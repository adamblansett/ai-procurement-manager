from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benchmarks.models import PricingBenchmark
from app.benchmarks.service import _percentile
from app.core.config import Settings
from app.core.governance import create_approval_request, record_audit_event
from app.core.llm import LLMRequest, LLMRouter
from app.core.models import ApprovalRequest, Vendor
from app.purchasing.models import BudgetAccount, PurchaseOrder, VendorQuote
from app.purchasing.schemas import PurchaseOrderRead, ValidationIssue


def _determine_approver_role(total_amount: float, settings: Settings) -> str:
    if total_amount > settings.po_vp_approval_threshold:
        return "vp_finance"
    if total_amount > settings.po_director_approval_threshold:
        return "finance_director"
    if total_amount > settings.po_auto_approve_threshold:
        return "finance_director"
    return "procurement_manager"


async def validate_purchase_order(
    db: AsyncSession,
    po: PurchaseOrder,
    settings: Settings,
    llm_router: LLMRouter,
    *,
    actor: str = "po-validator",
) -> PurchaseOrderRead:
    """Run arithmetic, quote, budget headroom, benchmark, and threshold checks on a PO."""
    vendor = await db.get(Vendor, po.vendor_id)
    vendor_name = vendor.name if vendor else "Unknown Vendor"

    issues: list[ValidationIssue] = []
    line_items: list[dict[str, Any]] = list(po.line_items_json or [])

    # 1. Line-item arithmetic checks
    if not line_items:
        issues.append(
            ValidationIssue(
                code="EMPTY_LINE_ITEMS",
                severity="fail",
                message="Purchase order must contain at least one line item.",
                field="line_items",
            )
        )
    else:
        computed_sum = 0.0
        for idx, item in enumerate(line_items):
            qty = int(item.get("quantity", 0))
            unit_price = float(item.get("unit_price", 0.0))
            line_total = float(item.get("line_total", 0.0))
            sku = str(item.get("sku_code", ""))
            if qty <= 0 or unit_price < 0:
                issues.append(
                    ValidationIssue(
                        code="INVALID_LINE_QUANTITY",
                        severity="fail",
                        message=(
                            f"Line {idx + 1} ({sku}) must have positive quantity and "
                            "non-negative unit price."
                        ),
                        field=f"line_items[{idx}]",
                    )
                )
            expected_line = round(qty * unit_price, 2)
            if abs(expected_line - round(line_total, 2)) > 0.01:
                issues.append(
                    ValidationIssue(
                        code="LINE_ARITHMETIC_MISMATCH",
                        severity="fail",
                        message=(
                            f"Line {idx + 1} ({sku}) total ${line_total:,.2f} does not equal "
                            f"{qty} x ${unit_price:,.2f} (${expected_line:,.2f})."
                        ),
                        field=f"line_items[{idx}].line_total",
                    )
                )
            computed_sum += line_total

        if abs(round(computed_sum, 2) - round(po.total_amount, 2)) > 0.01:
            issues.append(
                ValidationIssue(
                    code="TOTAL_ARITHMETIC_MISMATCH",
                    severity="fail",
                    message=(
                        f"PO total ${po.total_amount:,.2f} does not match sum of line items "
                        f"(${computed_sum:,.2f})."
                    ),
                    field="total_amount",
                )
            )

    # 2. Quote reconciliation checks
    if po.quote_id:
        quote = await db.get(VendorQuote, po.quote_id)
        if quote is None:
            issues.append(
                ValidationIssue(
                    code="QUOTE_NOT_FOUND",
                    severity="fail",
                    message=f"Referenced vendor quote '{po.quote_id}' does not exist.",
                    field="quote_id",
                )
            )
        else:
            if quote.vendor_id != po.vendor_id:
                issues.append(
                    ValidationIssue(
                        code="QUOTE_VENDOR_MISMATCH",
                        severity="fail",
                        message="Quote belongs to a different vendor than the purchase order.",
                        field="quote_id",
                    )
                )
            if quote.valid_until < date.today():
                issues.append(
                    ValidationIssue(
                        code="QUOTE_EXPIRED",
                        severity="warning",
                        message=(
                            f"Quote {quote.quote_number} expired on "
                            f"{quote.valid_until.isoformat()}."
                        ),
                        field="quote_id",
                    )
                )

            quote_lines = {
                str(q_item.get("sku_code", "")): q_item for q_item in (quote.line_items_json or [])
            }
            for item in line_items:
                sku = str(item.get("sku_code", ""))
                q_line = quote_lines.get(sku)
                if q_line is None:
                    issues.append(
                        ValidationIssue(
                            code="SKU_NOT_IN_QUOTE",
                            severity="fail",
                            message=f"SKU '{sku}' is not present on quote {quote.quote_number}.",
                            field="line_items",
                        )
                    )
                    continue
                po_price = float(item.get("unit_price", 0.0))
                q_price = float(q_line.get("unit_price", 0.0))
                if po_price > q_price + 0.001:
                    issues.append(
                        ValidationIssue(
                            code="PRICE_OVERCHARGE",
                            severity="fail",
                            message=(
                                f"SKU '{sku}' unit price ${po_price:,.2f} exceeds quoted rate "
                                f"${q_price:,.2f}."
                            ),
                            field="line_items",
                        )
                    )
                po_qty = int(item.get("quantity", 0))
                q_qty = int(q_line.get("quantity", 0))
                if po_qty > q_qty:
                    issues.append(
                        ValidationIssue(
                            code="QTY_EXCEEDS_QUOTE",
                            severity="warning",
                            message=(
                                f"SKU '{sku}' quantity {po_qty} exceeds quoted quantity {q_qty}."
                            ),
                            field="line_items",
                        )
                    )

            if po.total_amount > quote.total_amount + 0.01:
                issues.append(
                    ValidationIssue(
                        code="TOTAL_EXCEEDS_QUOTE",
                        severity="fail",
                        message=(
                            f"PO total ${po.total_amount:,.2f} exceeds quoted total "
                            f"${quote.total_amount:,.2f}."
                        ),
                        field="total_amount",
                    )
                )

    # 3. Budget-code and headroom verification
    budget_res = await db.execute(
        select(BudgetAccount).where(BudgetAccount.cost_center_code == po.cost_center_code)
    )
    budget = budget_res.scalar_one_or_none()
    if budget is None:
        issues.append(
            ValidationIssue(
                code="INVALID_BUDGET_CODE",
                severity="fail",
                message=f"Cost center '{po.cost_center_code}' was not found in active budgets.",
                field="cost_center_code",
            )
        )
    else:
        projected_committed = budget.committed_amount + po.total_amount
        remaining = max(0.0, budget.annual_budget - budget.committed_amount)
        if projected_committed > budget.annual_budget + 0.01:
            issues.append(
                ValidationIssue(
                    code="BUDGET_EXCEEDED",
                    severity="fail",
                    message=(
                        f"PO total ${po.total_amount:,.2f} exceeds remaining budget "
                        f"${remaining:,.2f} for {budget.cost_center_code} ({budget.department})."
                    ),
                    field="cost_center_code",
                )
            )
        elif budget.annual_budget > 0 and (projected_committed / budget.annual_budget) > 0.90:
            util_pct = (projected_committed / budget.annual_budget) * 100.0
            issues.append(
                ValidationIssue(
                    code="BUDGET_NEAR_LIMIT",
                    severity="warning",
                    message=(
                        f"Approving this PO brings {budget.cost_center_code} budget utilization "
                        f"to {util_pct:.1f}%."
                    ),
                    field="cost_center_code",
                )
            )

    # 4. Benchmark unit-price sanity check
    for item in line_items:
        sku = str(item.get("sku_code", ""))
        po_price = float(item.get("unit_price", 0.0))
        if not sku:
            continue
        bm_rows = (
            (await db.execute(select(PricingBenchmark).where(PricingBenchmark.sku_code == sku)))
            .scalars()
            .all()
        )
        if bm_rows:
            median = _percentile(sorted(r.quoted_unit_price for r in bm_rows), 50)
            if median > 0 and po_price > median * 1.15:
                over_pct = ((po_price - median) / median) * 100.0
                issues.append(
                    ValidationIssue(
                        code="ABOVE_BENCHMARK",
                        severity="warning",
                        message=(
                            f"SKU '{sku}' unit price ${po_price:,.2f} is {over_pct:.1f}% above "
                            f"benchmark median (${median:,.2f})."
                        ),
                        field="line_items",
                    )
                )

    # 5. Determine overall validation status and approver role
    has_fail = any(i.severity == "fail" for i in issues)
    has_warn = any(i.severity == "warning" for i in issues)
    validation_status = "fail" if has_fail else ("warning" if has_warn else "pass")
    required_role = _determine_approver_role(po.total_amount, settings)

    if has_fail:
        po.status = "blocked"
    elif po.status not in {"pending_approval", "approved", "rejected"}:
        po.status = "validated"

    po.validation_status = validation_status
    po.validation_issues_json = [issue.model_dump() for issue in issues]
    po.required_approver_role = required_role

    llm_resp = await llm_router.generate(
        LLMRequest(
            task="po_risk_summary",
            system_prompt=(
                "You are a finance controller summarizing purchase order validation checks."
            ),
            user_prompt=(
                f"Summarize validation outcome ({validation_status}) for PO {po.po_number} "
                f"(${po.total_amount:,.2f}) with {vendor_name}."
            ),
            context={
                "po_number": po.po_number,
                "vendor_name": vendor_name,
                "total_amount": po.total_amount,
                "validation_status": validation_status,
                "required_approver_role": required_role,
                "issues": [issue.message for issue in issues],
            },
        )
    )
    po.ai_risk_summary = llm_resp.content

    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        action="po.validated",
        entity_type="purchase_order",
        entity_id=po.id,
        summary=(
            f"Validated {po.po_number} ({vendor_name}, ${po.total_amount:,.2f}): "
            f"{validation_status} ({len(issues)} issues)."
        ),
        metadata={
            "validation_status": validation_status,
            "required_approver_role": required_role,
            "issue_codes": [issue.code for issue in issues],
        },
    )

    return PurchaseOrderRead.model_validate(po).model_copy(update={"vendor_name": vendor_name})


async def submit_po_for_approval(
    db: AsyncSession,
    po_id: str,
    *,
    requested_by: str,
    override_warnings: bool = False,
    justification: str = "",
) -> ApprovalRequest:
    po = await db.get(PurchaseOrder, po_id)
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if po.validation_status == "fail":
        raise HTTPException(
            status_code=422,
            detail=(
                "Cannot submit purchase order with failed validation checks; "
                "resolve blocking issues first."
            ),
        )
    if po.status in {"pending_approval", "approved"}:
        raise HTTPException(
            status_code=409,
            detail=f"Purchase order {po.po_number} is already {po.status}.",
        )

    vendor = await db.get(Vendor, po.vendor_id)
    vendor_name = vendor.name if vendor else "Vendor"
    warning_msgs = [
        str(i.get("message", ""))
        for i in (po.validation_issues_json or [])
        if i.get("severity") == "warning"
    ]
    summary_parts = [
        f"Approve PO {po.po_number} for {vendor_name} totaling ${po.total_amount:,.2f} "
        f"(Cost Center: {po.cost_center_code})."
    ]
    if warning_msgs:
        summary_parts.append("Warnings: " + "; ".join(warning_msgs))
    if justification:
        summary_parts.append(f"Requester Justification: {justification}")

    approval = await create_approval_request(
        db,
        entity_type="purchase_order",
        entity_id=po.id,
        action_type="approve_po",
        title=f"PO Approval: {po.po_number} ({vendor_name})",
        summary=" ".join(summary_parts),
        required_role=po.required_approver_role,
        requested_by=requested_by,
        amount_impact=po.total_amount,
        payload={
            "po_number": po.po_number,
            "cost_center_code": po.cost_center_code,
            "override_warnings": override_warnings,
            "justification": justification,
        },
    )
    po.status = "pending_approval"
    po.approval_request_id = approval.id
    await db.flush()
    return approval
