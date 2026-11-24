from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benchmarks.models import PricingBenchmark
from app.benchmarks.service import _percentile
from app.contracts.models import Contract, ContractClauseFinding
from app.core.governance import create_approval_request, record_audit_event
from app.core.llm import LLMRequest, LLMRouter
from app.core.models import ApprovalRequest, Vendor
from app.renewals.models import RenewalItem
from app.renewals.schemas import RenewalBriefResponse, RenewalRead


def compute_urgency(
    notice_deadline: date,
    auto_renew: bool,
    decision_status: str,
    today: date | None = None,
) -> tuple[int, str]:
    """Compute remaining days to notice deadline and operational urgency tier."""
    ref = today or date.today()
    days = (notice_deadline - ref).days
    if decision_status in {"renewed", "non_renewing", "notice_approved"}:
        return days, "healthy"
    if days < 0 and auto_renew:
        return days, "overdue"
    if days <= 30:
        return days, "critical"
    if days <= 90:
        return days, "upcoming"
    return days, "healthy"


def to_renewal_read(item: RenewalItem, vendor_name: str = "") -> RenewalRead:
    days_left, urgency = compute_urgency(
        item.notice_deadline, item.auto_renew, item.decision_status
    )
    projected = round(item.current_annual_value * (1.0 + item.proposed_uplift_pct / 100.0), 2)
    return RenewalRead.model_validate(item).model_copy(
        update={
            "vendor_name": vendor_name,
            "days_to_notice_deadline": days_left,
            "urgency": urgency,
            "projected_renewal_value": projected,
        }
    )


async def generate_renegotiation_brief(
    db: AsyncSession,
    renewal_id: str,
    llm_router: LLMRouter,
    *,
    actor: str = "procurement-strategist",
) -> RenewalBriefResponse:
    """Assemble commercial leverage, playbook redlines, and an AI renegotiation brief."""
    item = await db.get(RenewalItem, renewal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Renewal item not found")

    vendor = await db.get(Vendor, item.vendor_id)
    vendor_name = vendor.name if vendor else "Vendor"
    days_left, urgency = compute_urgency(
        item.notice_deadline, item.auto_renew, item.decision_status
    )

    projected_value = round(item.current_annual_value * (1.0 + item.proposed_uplift_pct / 100.0), 2)

    redlines: list[str] = []
    has_severe_contract_risk = False
    if item.contract_id:
        contract = await db.get(Contract, item.contract_id)
        if contract is not None and contract.risk_level in {"high", "critical"}:
            has_severe_contract_risk = True
        findings = (
            (
                await db.execute(
                    select(ContractClauseFinding)
                    .where(ContractClauseFinding.contract_id == item.contract_id)
                    .order_by(ContractClauseFinding.deviation_score.desc())
                )
            )
            .scalars()
            .all()
        )
        for f in findings:
            if f.status in {"deviation", "missing"} and f.redline_suggestion:
                redlines.append(f"[{f.clause_type}] {f.redline_suggestion}")

    if not redlines:
        redlines.append(
            "[price_uplift] Cap renewal uplifts at <= 3.0% and require 30-day non-renewal notice."
        )

    bm_rows = (
        (
            await db.execute(
                select(PricingBenchmark).where(PricingBenchmark.vendor_id == item.vendor_id)
            )
        )
        .scalars()
        .all()
    )
    if not bm_rows and vendor is not None:
        bm_rows = (
            (
                await db.execute(
                    select(PricingBenchmark).where(PricingBenchmark.category == vendor.category)
                )
            )
            .scalars()
            .all()
        )

    leverage_points: list[str] = []
    if item.proposed_uplift_pct > 3.0:
        leverage_points.append(
            f"Proposed {item.proposed_uplift_pct:.1f}% uplift exceeds our 3.0% target renewal cap "
            "and 5.0% commercial ceiling."
        )
    if bm_rows:
        prices = sorted(r.quoted_unit_price for r in bm_rows)
        p25 = _percentile(prices, 25)
        median = _percentile(prices, 50)
        avg_disc = round(sum(r.discount_pct for r in bm_rows) / len(bm_rows), 1)
        leverage_points.append(
            f"Market benchmark across {len(bm_rows)} peer quotes shows P25 at ${p25:,.2f} "
            f"(median ${median:,.2f}) and average negotiated discount of {avg_disc:.1f}%."
        )
    if item.auto_renew:
        leverage_points.append(
            f"Auto-renewal notice deadline is {item.notice_deadline.isoformat()} "
            f"({days_left} days remaining; urgency: {urgency}). Serve protective non-renewal "
            "notice early to preserve negotiation walk-away leverage."
        )
    if has_severe_contract_risk:
        leverage_points.append(
            "Linked contract carries high/critical playbook deviations; condition multi-year "
            "renewal on liability cap and auto-renewal redlines."
        )

    discount_factor = 0.92 if (has_severe_contract_risk or item.proposed_uplift_pct > 5.0) else 1.0
    target_value = min(projected_value, round(item.current_annual_value * discount_factor, 2))
    estimated_annual_savings = max(0.0, round(projected_value - target_value, 2))
    three_year_savings = round(estimated_annual_savings * 3.0, 2)

    deadline_iso = item.notice_deadline.isoformat()
    timeline = [
        (
            f"T-30 to T-15 before {deadline_iso}: Request HITL approval and send "
            "protective notice if pricing target is unmet."
        ),
        (
            f"T-14 to T-7 before {deadline_iso}: Exchange redlined Order Form & MSA "
            f"addendum targeting ${target_value:,.2f}/yr."
        ),
        (
            f"By {item.renewal_date.isoformat()}: Execute signed renewal agreement "
            "or confirm transition offboarding."
        ),
    ]

    draft_email = (
        f"Subject: {item.contract_title} — Protective Renewal & Commercial Discussion "
        f"({vendor_name})\n\n"
        f"Hello {vendor_name} Account Team,\n\n"
        f"Ahead of our {deadline_iso} notice window for {item.contract_title} "
        f"(renewing {item.renewal_date.isoformat()}), please treat this message as formal notice "
        f"that we do not intend to renew under the proposed {item.proposed_uplift_pct:.1f}% uplift "
        f"(${projected_value:,.2f}/yr).\n\n"
        f"We value our partnership and are prepared to execute a renewal at "
        f"${target_value:,.2f}/yr with a <= 3.0% future uplift cap and updated commercial terms. "
        f"Please send a revised Order Form by "
        f"{(item.notice_deadline - timedelta(days=7)).isoformat()}.\n\n"
        f"Best regards,\n{item.owner_name} — Procurement"
    )

    llm_resp = await llm_router.generate(
        LLMRequest(
            task="renewal_brief",
            system_prompt=(
                "You are a strategic procurement negotiator preparing an executive renewal dossier."
            ),
            user_prompt=(
                f"Generate a renegotiation brief for {vendor_name} ({item.contract_title}), "
                f"notice deadline {item.notice_deadline.isoformat()}."
            ),
            context={
                "vendor_name": vendor_name,
                "contract_title": item.contract_title,
                "current_annual_value": item.current_annual_value,
                "proposed_uplift_pct": item.proposed_uplift_pct,
                "projected_value": projected_value,
                "target_value": target_value,
                "estimated_savings": estimated_annual_savings,
                "days_to_notice_deadline": days_left,
                "leverage_points": leverage_points,
                "redlines": redlines,
                "draft_email": draft_email,
            },
        )
    )

    brief_data = {
        "projected_value": projected_value,
        "target_value": target_value,
        "estimated_annual_savings": estimated_annual_savings,
        "three_year_savings": three_year_savings,
        "leverage_points": leverage_points,
        "clause_redlines": redlines,
        "recommended_timeline": timeline,
        "draft_notice_email": draft_email,
        "llm_provider": llm_resp.provider,
    }

    item.brief_markdown = llm_resp.content
    item.brief_data_json = brief_data
    item.brief_generated_at = datetime.now(UTC)
    if item.decision_status == "monitoring":
        item.decision_status = "renegotiating"

    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        action="renewal.brief_generated",
        entity_type="renewal_item",
        entity_id=item.id,
        summary=(
            f"Generated renegotiation brief for {vendor_name} — {item.contract_title} "
            f"(target savings ${estimated_annual_savings:,.2f}/yr)."
        ),
        metadata={
            "target_value": target_value,
            "estimated_annual_savings": estimated_annual_savings,
            "llm_provider": llm_resp.provider,
        },
    )

    return RenewalBriefResponse(
        renewal=to_renewal_read(item, vendor_name),
        projected_value=projected_value,
        target_value=target_value,
        estimated_annual_savings=estimated_annual_savings,
        three_year_savings=three_year_savings,
        leverage_points=leverage_points,
        clause_redlines=redlines,
        recommended_timeline=timeline,
        draft_notice_email=draft_email,
        brief_markdown=llm_resp.content,
    )


async def request_renewal_action(
    db: AsyncSession,
    renewal_id: str,
    *,
    action_type: str,
    requested_by: str,
    notes: str = "",
) -> ApprovalRequest:
    item = await db.get(RenewalItem, renewal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Renewal item not found")

    vendor = await db.get(Vendor, item.vendor_id)
    vendor_name = vendor.name if vendor else "Vendor"
    if item.current_annual_value > 150000.0:
        required_role = "vp_finance"
    elif item.current_annual_value > 50000.0:
        required_role = "finance_director"
    else:
        required_role = "procurement_manager"

    action_label = action_type.replace("_", " ").title()
    summary = (
        f"HITL confirmation for '{action_label}' on {vendor_name} — {item.contract_title} "
        f"(annual value ${item.current_annual_value:,.2f}, notice deadline "
        f"{item.notice_deadline.isoformat()}). {notes}".strip()
    )
    approval = await create_approval_request(
        db,
        entity_type="renewal_action",
        entity_id=item.id,
        action_type=action_type,
        title=f"Renewal {action_label}: {vendor_name}",
        summary=summary,
        required_role=required_role,
        requested_by=requested_by,
        amount_impact=item.current_annual_value,
        payload={
            "contract_title": item.contract_title,
            "notice_deadline": item.notice_deadline.isoformat(),
            "proposed_uplift_pct": item.proposed_uplift_pct,
        },
    )
    item.decision_status = "notice_pending_approval"
    await db.flush()
    return approval
