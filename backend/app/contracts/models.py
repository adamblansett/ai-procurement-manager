import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PlaybookRule(Base):
    """Commercial and legal playbook baseline for clause comparison."""

    __tablename__ = "playbook_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(140))
    clause_type: Mapped[str] = mapped_column(String(64), index=True)
    preferred_position: Mapped[str] = mapped_column(Text)
    fallback_position: Mapped[str] = mapped_column(Text, default="")
    max_acceptable_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(24), default="medium")
    guidance: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class Contract(Base):
    """Ingested vendor MSA, DPA, Order Form, or SOW."""

    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id: Mapped[str] = mapped_column(String(36), ForeignKey("vendors.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    contract_type: Mapped[str] = mapped_column(String(32), default="MSA")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_value: Mapped[float] = mapped_column(Float, default=0.0)
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(24), default="low")
    comparison_summary: Mapped[str] = mapped_column(Text, default="")
    llm_provider_used: Mapped[str] = mapped_column(String(32), default="mock")
    pii_redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_compared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ContractClauseFinding(Base):
    """Per-clause playbook diff finding generated for a contract."""

    __tablename__ = "contract_clause_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    clause_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24))
    severity: Mapped[str] = mapped_column(String(24))
    vendor_excerpt: Mapped[str] = mapped_column(Text, default="")
    playbook_position: Mapped[str] = mapped_column(Text)
    redline_suggestion: Mapped[str] = mapped_column(Text, default="")
    deviation_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
