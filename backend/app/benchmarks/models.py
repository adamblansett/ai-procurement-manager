import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PricingBenchmark(Base):
    """Normalized historical quote, executed contract, or market unit-price record."""

    __tablename__ = "pricing_benchmarks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vendors.id"), nullable=True, index=True
    )
    sku_code: Mapped[str] = mapped_column(String(80), index=True)
    sku_name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), index=True)
    unit_type: Mapped[str] = mapped_column(String(48))
    volume_tier: Mapped[str] = mapped_column(String(24), default="51-250")
    quoted_unit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    annual_uplift_pct: Mapped[float] = mapped_column(Float, default=0.0)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="historical_quote")
    effective_year: Mapped[int] = mapped_column(Integer, default=2026)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
