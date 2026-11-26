import csv
import io
import json
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.models import Contract
from app.core.auth import TokenPayload, get_optional_current_user, role_can_approve
from app.core.database import get_db
from app.core.governance import record_audit_event, verify_audit_chain
from app.core.models import ApprovalRequest, AuditLog
from app.purchasing.models import BudgetAccount, PurchaseOrder
from app.renewals.models import RenewalItem

router = APIRouter(prefix="/governance", tags=["governance"])


class ApprovalRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    action_type: str
    title: str
    summary: str
    required_role: str
    amount_impact: float
    status: str
    requested_by: str
    decided_by: str | None
    decision_notes: str
    payload_json: dict[str, Any]
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    decided_by: str = Field(min_length=2, max_length=120)
    decision_notes: str = ""


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sequence_num: int
    actor: str
    action: str
    entity_type: str
    entity_id: str
    summary: str
    metadata_json: dict[str, Any]
    prev_hash: str
    entry_hash: str
    created_at: datetime


class AuditChainVerificationRead(BaseModel):
    valid: bool
    total_entries: int
    latest_hash: str | None
    broken_at_sequence: int | None


@router.get("/approvals", response_model=list[ApprovalRequestRead])
async def list_approvals(
    status: str | None = None,
    entity_type: str | None = None,
    required_role: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequest]:
    """List human-in-the-loop approval requests with optional status/role filters."""
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    if entity_type:
        stmt = stmt.where(ApprovalRequest.entity_type == entity_type)
    if required_role:
        stmt = stmt.where(ApprovalRequest.required_role == required_role)
    return list((await db.execute(stmt)).scalars().all())


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalRequestRead)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload | None = Depends(get_optional_current_user),
) -> ApprovalRequest:
    """Approve or reject a pending HITL request with RBAC and separation-of-duties checks."""
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval request already resolved with status '{approval.status}'.",
        )

    if current_user is not None:
        if not role_can_approve(current_user.role, approval.required_role):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Role '{current_user.role}' cannot decide approvals requiring "
                    f"'{approval.required_role}'."
                ),
            )
        effective_actor = current_user.full_name
    else:
        effective_actor = payload.decided_by

    if effective_actor.strip().lower() == approval.requested_by.strip().lower():
        raise HTTPException(
            status_code=403,
            detail=(
                "Separation of duties violation: requester cannot approve or reject "
                "their own request."
            ),
        )

    approval.status = payload.decision
    approval.decided_by = effective_actor
    approval.decision_notes = payload.decision_notes
    approval.decided_at = datetime.now(UTC)

    # Propagate HITL decision to the governed domain record.
    if approval.entity_type == "purchase_order":
        po = await db.get(PurchaseOrder, approval.entity_id)
        if po is not None:
            if payload.decision == "approved":
                po.status = "approved"
                budget_res = await db.execute(
                    select(BudgetAccount).where(
                        BudgetAccount.cost_center_code == po.cost_center_code
                    )
                )
                budget = budget_res.scalar_one_or_none()
                if budget is not None:
                    budget.committed_amount = round(budget.committed_amount + po.total_amount, 2)
            else:
                po.status = "rejected"
    elif approval.entity_type == "contract_review":
        contract = await db.get(Contract, approval.entity_id)
        if contract is not None:
            contract.status = "approved" if payload.decision == "approved" else "redline_required"
    elif approval.entity_type == "renewal_action":
        renewal = await db.get(RenewalItem, approval.entity_id)
        if renewal is not None:
            if payload.decision == "approved":
                if approval.action_type == "send_non_renewal_notice":
                    renewal.decision_status = "notice_approved"
                elif approval.action_type == "approve_renewal_terms":
                    renewal.decision_status = "renewed"
                else:
                    renewal.decision_status = "renegotiating"
            else:
                renewal.decision_status = "renegotiating"

    await db.flush()
    note_text = payload.decision_notes or "No notes"
    await record_audit_event(
        db,
        actor=effective_actor,
        action=f"approval.{payload.decision}",
        entity_type=approval.entity_type,
        entity_id=approval.entity_id,
        summary=f"{payload.decision.upper()} '{approval.title}': {note_text}",
        metadata={
            "approval_id": approval.id,
            "required_role": approval.required_role,
            "amount_impact": approval.amount_impact,
        },
    )
    await db.commit()
    await db.refresh(approval)
    return approval


@router.get("/audit-logs", response_model=list[AuditLogRead])
async def list_audit_logs(
    entity_type: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    """Return immutable hash-chained audit trail records ordered newest-first."""
    stmt = select(AuditLog).order_by(AuditLog.sequence_num.desc()).limit(limit)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/audit-logs/verify", response_model=AuditChainVerificationRead)
async def verify_audit_log_chain(
    db: AsyncSession = Depends(get_db),
) -> AuditChainVerificationRead:
    """Verify cryptographic SHA-256 continuity across the entire audit ledger."""
    result = await verify_audit_chain(db)
    return AuditChainVerificationRead(**result)


@router.get("/audit-logs/export")
async def export_audit_logs(
    export_format: Literal["csv", "json"] = Query(default="json"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export immutable hash-chained audit logs as CSV or signed JSON bundle."""
    rows = (
        (await db.execute(select(AuditLog).order_by(AuditLog.sequence_num.asc()))).scalars().all()
    )
    if export_format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "sequence_num",
                "created_at",
                "actor",
                "action",
                "entity_type",
                "entity_id",
                "summary",
                "prev_hash",
                "entry_hash",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.sequence_num,
                    row.created_at.isoformat(),
                    row.actor,
                    row.action,
                    row.entity_type,
                    row.entity_id,
                    row.summary,
                    row.prev_hash,
                    row.entry_hash,
                ]
            )
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="audit_ledger.csv"'},
        )

    verification = await verify_audit_chain(db)
    bundle = {
        "chain_verification": verification,
        "entries": [AuditLogRead.model_validate(row).model_dump(mode="json") for row in rows],
    }
    return Response(
        content=json.dumps(bundle, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit_ledger_signed.json"'},
    )
