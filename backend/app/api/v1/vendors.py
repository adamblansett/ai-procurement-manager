from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.governance import record_audit_event
from app.core.models import Vendor

router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    tier: Literal["strategic", "preferred", "standard"] = "standard"
    status: Literal["active", "under_review", "offboarding"] = "active"
    primary_contact_name: str = ""
    primary_contact_email: str = ""
    annual_spend: float = Field(default=0.0, ge=0.0)
    risk_score: int = Field(default=20, ge=0, le=100)
    payment_terms_days: int = Field(default=30, ge=0, le=180)
    notes: str = ""


class VendorUpdate(BaseModel):
    category: str | None = None
    tier: Literal["strategic", "preferred", "standard"] | None = None
    status: Literal["active", "under_review", "offboarding"] | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    annual_spend: float | None = Field(default=None, ge=0.0)
    risk_score: int | None = Field(default=None, ge=0, le=100)
    payment_terms_days: int | None = Field(default=None, ge=0, le=180)
    notes: str | None = None


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    tier: str
    status: str
    primary_contact_name: str
    primary_contact_email: str
    annual_spend: float
    risk_score: int
    payment_terms_days: int
    notes: str
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[VendorRead])
async def list_vendors(
    category: str | None = None,
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Vendor]:
    """List registered suppliers ordered by annual spend descending."""
    stmt = select(Vendor).order_by(Vendor.annual_spend.desc(), Vendor.name.asc())
    if category:
        stmt = stmt.where(Vendor.category == category)
    if status_filter:
        stmt = stmt.where(Vendor.status == status_filter)
    return list((await db.execute(stmt)).scalars().all())


@router.post("", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
async def create_vendor(payload: VendorCreate, db: AsyncSession = Depends(get_db)) -> Vendor:
    """Create a vendor directory entry and record an immutable audit trail event."""
    existing = (
        await db.execute(select(Vendor).where(Vendor.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Vendor with this name already exists")

    vendor = Vendor(**payload.model_dump())
    db.add(vendor)
    await db.flush()
    await record_audit_event(
        db,
        actor="procurement-admin",
        action="vendor.created",
        entity_type="vendor",
        entity_id=vendor.id,
        summary=f"Created vendor '{vendor.name}' ({vendor.category}, tier={vendor.tier}).",
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.get("/{vendor_id}", response_model=VendorRead)
async def get_vendor(vendor_id: str, db: AsyncSession = Depends(get_db)) -> Vendor:
    """Fetch a single vendor by ID."""
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


@router.patch("/{vendor_id}", response_model=VendorRead)
async def update_vendor(
    vendor_id: str, payload: VendorUpdate, db: AsyncSession = Depends(get_db)
) -> Vendor:
    """Update vendor commercial metadata and record an audit trail event."""
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(vendor, field_name, value)
    await db.flush()
    await record_audit_event(
        db,
        actor="procurement-admin",
        action="vendor.updated",
        entity_type="vendor",
        entity_id=vendor.id,
        summary=f"Updated vendor '{vendor.name}' (status={vendor.status}, tier={vendor.tier}).",
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor
