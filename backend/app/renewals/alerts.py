from datetime import datetime
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.governance import record_audit_event
from app.core.models import Vendor
from app.renewals.models import RenewalAlertDispatch, RenewalItem
from app.renewals.service import compute_urgency

logger = structlog.get_logger(__name__)

ALERT_THRESHOLDS: tuple[int, ...] = (0, 7, 30, 60, 90)


class RenewalAlertDispatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    renewal_id: str
    threshold_days: int
    channel: str
    delivery_status: str
    recipient_target: str
    message_summary: str
    dispatched_at: datetime


def _matching_threshold(days_left: int) -> int | None:
    for threshold in ALERT_THRESHOLDS:
        if days_left <= threshold:
            return threshold
    return None


async def run_renewal_alert_sweep(
    db: AsyncSession,
    settings: Settings,
    *,
    actor: str = "renewal-scheduler",
) -> dict[str, Any]:
    """Check renewal notice windows and dispatch deduplicated threshold alerts."""
    items = (
        (await db.execute(select(RenewalItem).order_by(RenewalItem.notice_deadline.asc())))
        .scalars()
        .all()
    )
    vendors = (await db.execute(select(Vendor))).scalars().all()
    vendor_names = {v.id: v.name for v in vendors}

    dispatched: list[RenewalAlertDispatch] = []
    checked_count = 0

    for item in items:
        if item.decision_status in {"renewed", "non_renewing", "notice_approved"}:
            continue
        checked_count += 1
        days_left, urgency = compute_urgency(
            item.notice_deadline, item.auto_renew, item.decision_status
        )
        threshold = _matching_threshold(days_left)
        if threshold is None:
            continue

        existing = (
            await db.execute(
                select(RenewalAlertDispatch).where(
                    RenewalAlertDispatch.renewal_id == item.id,
                    RenewalAlertDispatch.threshold_days == threshold,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        vendor_name = vendor_names.get(item.vendor_id, "Vendor")
        summary = (
            f"[{urgency.upper()}] {vendor_name} — {item.contract_title}: "
            f"notice deadline {item.notice_deadline.isoformat()} ({days_left}d remaining, "
            f"${item.current_annual_value:,.2f}/yr, +{item.proposed_uplift_pct:.1f}% uplift)."
        )

        channel = "in_app"
        delivery_status = "simulated"
        recipient = item.owner_name
        webhook_url = settings.alert_webhook_url.strip()
        if webhook_url:
            channel = "webhook"
            recipient = webhook_url
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        webhook_url,
                        json={
                            "event": "renewal.notice_alert",
                            "threshold_days": threshold,
                            "urgency": urgency,
                            "days_remaining": days_left,
                            "vendor_name": vendor_name,
                            "contract_title": item.contract_title,
                            "notice_deadline": item.notice_deadline.isoformat(),
                            "summary": summary,
                        },
                    )
                    resp.raise_for_status()
                delivery_status = "sent"
            except Exception as exc:  # noqa: BLE001
                delivery_status = "failed"
                logger.warning("renewal_webhook_failed", url=webhook_url, error=str(exc))

        record = RenewalAlertDispatch(
            renewal_id=item.id,
            threshold_days=threshold,
            channel=channel,
            delivery_status=delivery_status,
            recipient_target=recipient,
            message_summary=summary,
        )
        db.add(record)
        await db.flush()
        await record_audit_event(
            db,
            actor=actor,
            action="renewal.alert_dispatched",
            entity_type="renewal_item",
            entity_id=item.id,
            summary=summary,
            metadata={
                "threshold_days": threshold,
                "channel": channel,
                "delivery_status": delivery_status,
            },
        )
        dispatched.append(record)

    return {
        "checked_count": checked_count,
        "dispatched_count": len(dispatched),
        "dispatches": [RenewalAlertDispatchRead.model_validate(d).model_dump() for d in dispatched],
    }


async def list_alert_dispatches(db: AsyncSession) -> list[RenewalAlertDispatch]:
    """Return dispatched renewal alerts ordered newest-first."""
    rows = (
        (
            await db.execute(
                select(RenewalAlertDispatch)
                .order_by(RenewalAlertDispatch.dispatched_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
