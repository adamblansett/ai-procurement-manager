import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ApprovalRequest, AuditLog

GENESIS_HASH = "0" * 64


def compute_audit_hash(
    prev_hash: str,
    sequence_num: int,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    metadata: dict[str, Any],
) -> str:
    """Compute a deterministic SHA-256 hash linking an audit record to its predecessor."""
    canonical = json.dumps(
        {
            "prev_hash": prev_hash,
            "sequence_num": sequence_num,
            "actor": actor,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary": summary,
            "metadata": metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def record_audit_event(
    db: AsyncSession,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an immutable, hash-chained audit record to the ledger."""
    payload = metadata or {}
    latest_result = await db.execute(
        select(AuditLog).order_by(AuditLog.sequence_num.desc()).limit(1)
    )
    latest = latest_result.scalar_one_or_none()
    next_seq = (latest.sequence_num + 1) if latest is not None else 1
    prev_hash = latest.entry_hash if latest is not None else GENESIS_HASH

    entry_hash = compute_audit_hash(
        prev_hash=prev_hash,
        sequence_num=next_seq,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        metadata=payload,
    )
    entry = AuditLog(
        sequence_num=next_seq,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        metadata_json=payload,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_audit_chain(db: AsyncSession) -> dict[str, Any]:
    """Recompute and verify hash-chain integrity across every persisted audit record."""
    rows = (
        (await db.execute(select(AuditLog).order_by(AuditLog.sequence_num.asc()))).scalars().all()
    )
    expected_prev = GENESIS_HASH
    latest_hash: str | None = None

    for expected_seq, row in enumerate(rows, start=1):
        if row.sequence_num != expected_seq or row.prev_hash != expected_prev:
            return {
                "valid": False,
                "total_entries": len(rows),
                "latest_hash": latest_hash,
                "broken_at_sequence": row.sequence_num,
            }
        expected_hash = compute_audit_hash(
            prev_hash=row.prev_hash,
            sequence_num=row.sequence_num,
            actor=row.actor,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            summary=row.summary,
            metadata=row.metadata_json,
        )
        if row.entry_hash != expected_hash:
            return {
                "valid": False,
                "total_entries": len(rows),
                "latest_hash": latest_hash,
                "broken_at_sequence": row.sequence_num,
            }
        expected_prev = row.entry_hash
        latest_hash = row.entry_hash

    return {
        "valid": True,
        "total_entries": len(rows),
        "latest_hash": latest_hash,
        "broken_at_sequence": None,
    }


async def create_approval_request(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    action_type: str,
    title: str,
    summary: str,
    required_role: str,
    requested_by: str,
    amount_impact: float = 0.0,
    payload: dict[str, Any] | None = None,
) -> ApprovalRequest:
    """Create a pending HITL approval gate and record an immutable audit trail entry."""
    approval = ApprovalRequest(
        entity_type=entity_type,
        entity_id=entity_id,
        action_type=action_type,
        title=title,
        summary=summary,
        required_role=required_role,
        amount_impact=round(amount_impact, 2),
        status="pending",
        requested_by=requested_by,
        payload_json=payload or {},
    )
    db.add(approval)
    await db.flush()

    await record_audit_event(
        db,
        actor=requested_by,
        action="approval.requested",
        entity_type=entity_type,
        entity_id=entity_id,
        summary=f"Approval requested ({required_role}): {title}",
        metadata={
            "approval_id": approval.id,
            "action_type": action_type,
            "required_role": required_role,
            "amount_impact": round(amount_impact, 2),
        },
    )
    return approval
