import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BudgetAccount(Base):
    """Cost center budget envelope checked during PO validation and approval."""

    __tablename__ = "budget_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cost_center_code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    department: Mapped[str] = mapped_column(String(120))
    fiscal_year: Mapped[int] = mapped_column(Integer, default=2026)
    annual_budget: Mapped[float] = mapped_column(Float)
    committed_amount: Mapped[float] = mapped_column(Float, default=0.0)
    owner_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class VendorQuote(Base):
    """Quoted line items and commercial validity used to reconcile purchase orders."""

    __tablename__ = "vendor_quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id: Mapped[str] = mapped_column(String(36), ForeignKey("vendors.id"), index=True)
    quote_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    valid_until: Mapped[date] = mapped_column(Date)
    total_amount: Mapped[float] = mapped_column(Float)
    line_items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class PurchaseOrder(Base):
    """Purchase order validated against quotes, budgets, benchmarks, and approval limits."""

    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    po_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    vendor_id: Mapped[str] = mapped_column(String(36), ForeignKey("vendors.id"), index=True)
    quote_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vendor_quotes.id"), nullable=True, index=True
    )
    cost_center_code: Mapped[str] = mapped_column(String(48), index=True)
    requester_name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    total_amount: Mapped[float] = mapped_column(Float)
    line_items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    validation_status: Mapped[str] = mapped_column(String(24), default="pass")
    validation_issues_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    required_approver_role: Mapped[str] = mapped_column(String(48), default="procurement_manager")
    approval_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ai_risk_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )
