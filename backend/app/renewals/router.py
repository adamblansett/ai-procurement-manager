from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.governance import record_audit_event
from app.core.llm import LLMRouter, get_llm_router
from app.core.models import Vendor
from app.renewals.models import RenewalItem
from app.renewals.schemas import (
    RenewalActionRequest,
    RenewalBriefResponse,
    RenewalCreate,
    RenewalRead,
    RenewalUpdate,
)
from app.renewals.service import (
    generate_renegotiation_brief,
    request_renewal_action,
    to_renewal_read,
)

router = APIRouter(prefix="/renewals", tags=["renewals"])


@router.get("", response_model=list[RenewalRead])
async def list_renewals(
    urgency: str | None = None,
    decision_status: str | None = None,
    days_window: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[RenewalRead]:
    """List upcoming renewals sorted by notice deadline with urgency filtering."""
    stmt = select(RenewalItem).order_by(RenewalItem.notice_deadline.asc())
    if decision_status:
        stmt = stmt.where(RenewalItem.decision_status == decision_status)
    rows = (await db.execute(stmt)).scalars().all()

    vendor_ids = {r.vendor_id for r in rows}
    vendor_names: dict[str, str] = {}
    if vendor_ids:
        vendors = (
            (await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))).scalars().all()
        )
        vendor_names = {v.id: v.name for v in vendors}

    results = [to_renewal_read(row, vendor_names.get(row.vendor_id, "")) for row in rows]
    if urgency:
        results = [item for item in results if item.urgency == urgency]
    if days_window is not None:
        results = [item for item in results if item.days_to_notice_deadline <= days_window]
    return results


@router.post("", response_model=RenewalRead, status_code=status.HTTP_201_CREATED)
async def create_renewal(payload: RenewalCreate, db: AsyncSession = Depends(get_db)) -> RenewalRead:
    """Register a vendor contract renewal and compute its non-renewal notice deadline."""
    vendor = await db.get(Vendor, payload.vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    notice_deadline = payload.renewal_date - timedelta(days=payload.notice_period_days)
    item = RenewalItem(
        vendor_id=payload.vendor_id,
        contract_id=payload.contract_id,
        contract_title=payload.contract_title,
        renewal_date=payload.renewal_date,
        notice_period_days=payload.notice_period_days,
        notice_deadline=notice_deadline,
        auto_renew=payload.auto_renew,
        current_annual_value=round(payload.current_annual_value, 2),
        proposed_uplift_pct=round(payload.proposed_uplift_pct, 2),
        owner_name=payload.owner_name,
    )
    db.add(item)
    await db.flush()
    await record_audit_event(
        db,
        actor=payload.owner_name,
        action="renewal.created",
        entity_type="renewal_item",
        entity_id=item.id,
        summary=(
            f"Tracked renewal '{item.contract_title}' ({vendor.name}), "
            f"notice deadline {notice_deadline.isoformat()}."
        ),
    )
    await db.commit()
    await db.refresh(item)
    return to_renewal_read(item, vendor.name)


@router.get("/{renewal_id}", response_model=RenewalRead)
async def get_renewal(renewal_id: str, db: AsyncSession = Depends(get_db)) -> RenewalRead:
    """Retrieve a tracked renewal item by ID."""
    item = await db.get(RenewalItem, renewal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Renewal item not found")
    vendor = await db.get(Vendor, item.vendor_id)
    return to_renewal_read(item, vendor.name if vendor else "")


@router.patch("/{renewal_id}", response_model=RenewalRead)
async def update_renewal(
    renewal_id: str,
    payload: RenewalUpdate,
    db: AsyncSession = Depends(get_db),
) -> RenewalRead:
    """Update renewal parameters or status and recompute the notice deadline."""
    item = await db.get(RenewalItem, renewal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Renewal item not found")

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(item, field_name, value)
    item.notice_deadline = item.renewal_date - timedelta(days=item.notice_period_days)

    await db.flush()
    await record_audit_event(
        db,
        actor=item.owner_name,
        action="renewal.updated",
        entity_type="renewal_item",
        entity_id=item.id,
        summary=f"Updated renewal '{item.contract_title}' (status={item.decision_status}).",
    )
    await db.commit()
    await db.refresh(item)
    vendor = await db.get(Vendor, item.vendor_id)
    return to_renewal_read(item, vendor.name if vendor else "")


@router.post("/{renewal_id}/generate-brief", response_model=RenewalBriefResponse)
async def build_renegotiation_brief(
    renewal_id: str,
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> RenewalBriefResponse:
    """Synthesize an AI renegotiation brief from linked contract deviations and benchmarks."""
    response = await generate_renegotiation_brief(db, renewal_id, llm_router)
    await db.commit()
    return response


@router.post("/{renewal_id}/request-action", status_code=status.HTTP_201_CREATED)
async def submit_renewal_action(
    renewal_id: str,
    payload: RenewalActionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Queue a high-impact renewal notice or term approval for human-in-the-loop sign-off."""
    approval = await request_renewal_action(
        db,
        renewal_id,
        action_type=payload.action_type,
        requested_by=payload.requested_by,
        notes=payload.notes,
    )
    await db.commit()
    return {
        "approval_id": approval.id,
        "status": approval.status,
        "required_role": approval.required_role,
    }
