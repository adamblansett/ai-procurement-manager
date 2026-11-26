import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RenewalItem(Base):
    """Tracked supplier contract renewal, notice deadline, and renegotiation brief."""

    __tablename__ = "renewal_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id: Mapped[str] = mapped_column(String(36), ForeignKey("vendors.id"), index=True)
    contract_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contracts.id"), nullable=True, index=True
    )
    contract_title: Mapped[str] = mapped_column(String(200))
    renewal_date: Mapped[date] = mapped_column(Date, index=True)
    notice_period_days: Mapped[int] = mapped_column(Integer, default=60)
    notice_deadline: Mapped[date] = mapped_column(Date, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    current_annual_value: Mapped[float] = mapped_column(Float)
    proposed_uplift_pct: Mapped[float] = mapped_column(Float, default=0.0)
    owner_name: Mapped[str] = mapped_column(String(120))
    decision_status: Mapped[str] = mapped_column(String(32), default="monitoring", index=True)
    brief_markdown: Mapped[str] = mapped_column(Text, default="")
    brief_data_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    brief_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )


class RenewalAlertDispatch(Base):
    """Deduplicated threshold alert dispatch history for upcoming renewal notice deadlines."""

    __tablename__ = "renewal_alert_dispatches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    renewal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("renewal_items.id", ondelete="CASCADE"), index=True
    )
    threshold_days: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(32), default="in_app")
    delivery_status: Mapped[str] = mapped_column(String(24), default="simulated")
    recipient_target: Mapped[str] = mapped_column(String(240), default="")
    message_summary: Mapped[str] = mapped_column(Text)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
