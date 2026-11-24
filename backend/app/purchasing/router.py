from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_app_settings, get_db
from app.core.governance import record_audit_event
from app.core.llm import LLMRouter, get_llm_router
from app.core.models import Vendor
from app.purchasing.models import BudgetAccount, PurchaseOrder, VendorQuote
from app.purchasing.schemas import (
    BudgetAccountCreate,
    BudgetAccountRead,
    PurchaseOrderCreate,
    PurchaseOrderRead,
    PurchaseOrderSubmitRequest,
    VendorQuoteCreate,
    VendorQuoteRead,
)
from app.purchasing.service import submit_po_for_approval, validate_purchase_order

router = APIRouter(prefix="/purchasing", tags=["purchasing"])


def _to_budget_read(account: BudgetAccount) -> BudgetAccountRead:
    remaining = round(max(0.0, account.annual_budget - account.committed_amount), 2)
    return BudgetAccountRead.model_validate(account).model_copy(
        update={"remaining_budget": remaining}
    )


@router.get("/budgets", response_model=list[BudgetAccountRead])
async def list_budgets(db: AsyncSession = Depends(get_db)) -> list[BudgetAccountRead]:
    """List cost-center budget accounts and remaining headroom."""
    rows = (
        (await db.execute(select(BudgetAccount).order_by(BudgetAccount.cost_center_code.asc())))
        .scalars()
        .all()
    )
    return [_to_budget_read(row) for row in rows]


@router.post("/budgets", response_model=BudgetAccountRead, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetAccountCreate, db: AsyncSession = Depends(get_db)
) -> BudgetAccountRead:
    """Create a cost-center budget envelope."""
    existing = (
        await db.execute(
            select(BudgetAccount).where(BudgetAccount.cost_center_code == payload.cost_center_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Cost center code already exists")

    account = BudgetAccount(**payload.model_dump())
    db.add(account)
    await db.flush()
    await record_audit_event(
        db,
        actor="finance-admin",
        action="budget.created",
        entity_type="budget_account",
        entity_id=account.id,
        summary=(
            f"Created budget {account.cost_center_code} ({account.department}) "
            f"with ${account.annual_budget:,.2f} FY{account.fiscal_year} envelope."
        ),
    )
    await db.commit()
    await db.refresh(account)
    return _to_budget_read(account)


@router.get("/quotes", response_model=list[VendorQuoteRead])
async def list_quotes(db: AsyncSession = Depends(get_db)) -> list[VendorQuoteRead]:
    """List vendor quotes available for PO reconciliation."""
    rows = (
        (await db.execute(select(VendorQuote).order_by(VendorQuote.created_at.desc())))
        .scalars()
        .all()
    )
    vendor_ids = {r.vendor_id for r in rows}
    vendor_names: dict[str, str] = {}
    if vendor_ids:
        vendors = (
            (await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))).scalars().all()
        )
        vendor_names = {v.id: v.name for v in vendors}
    return [
        VendorQuoteRead.model_validate(row).model_copy(
            update={"vendor_name": vendor_names.get(row.vendor_id, "")}
        )
        for row in rows
    ]


@router.post("/quotes", response_model=VendorQuoteRead, status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: VendorQuoteCreate, db: AsyncSession = Depends(get_db)
) -> VendorQuoteRead:
    """Register a vendor quote for quote-to-PO line-item verification."""
    vendor = await db.get(Vendor, payload.vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    existing = (
        await db.execute(
            select(VendorQuote).where(VendorQuote.quote_number == payload.quote_number)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Quote number already exists")

    total = (
        round(payload.total_amount, 2)
        if payload.total_amount is not None
        else round(sum(item.line_total for item in payload.line_items), 2)
    )
    quote = VendorQuote(
        vendor_id=payload.vendor_id,
        quote_number=payload.quote_number,
        currency=payload.currency,
        valid_until=payload.valid_until,
        total_amount=total,
        line_items_json=[item.model_dump() for item in payload.line_items],
    )
    db.add(quote)
    await db.flush()
    await record_audit_event(
        db,
        actor="procurement-user",
        action="quote.created",
        entity_type="vendor_quote",
        entity_id=quote.id,
        summary=f"Registered vendor quote {quote.quote_number} ({vendor.name}, ${total:,.2f}).",
    )
    await db.commit()
    await db.refresh(quote)
    return VendorQuoteRead.model_validate(quote).model_copy(update={"vendor_name": vendor.name})


@router.get("/orders", response_model=list[PurchaseOrderRead])
async def list_purchase_orders(
    status_filter: str | None = None,
    validation_status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PurchaseOrderRead]:
    """List purchase orders with validation findings and approval status."""
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    if status_filter:
        stmt = stmt.where(PurchaseOrder.status == status_filter)
    if validation_status:
        stmt = stmt.where(PurchaseOrder.validation_status == validation_status)
    rows = (await db.execute(stmt)).scalars().all()

    vendor_ids = {r.vendor_id for r in rows}
    vendor_names: dict[str, str] = {}
    if vendor_ids:
        vendors = (
            (await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))).scalars().all()
        )
        vendor_names = {v.id: v.name for v in vendors}
    return [
        PurchaseOrderRead.model_validate(row).model_copy(
            update={"vendor_name": vendor_names.get(row.vendor_id, "")}
        )
        for row in rows
    ]


@router.post("/orders", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> PurchaseOrderRead:
    """Create a purchase order and immediately execute automated PO validation checks."""
    vendor = await db.get(Vendor, payload.vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    existing = (
        await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == payload.po_number))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="PO number already exists")

    total = (
        round(payload.total_amount, 2)
        if payload.total_amount is not None
        else round(sum(item.line_total for item in payload.line_items), 2)
    )
    po = PurchaseOrder(
        po_number=payload.po_number,
        vendor_id=payload.vendor_id,
        quote_id=payload.quote_id,
        cost_center_code=payload.cost_center_code,
        requester_name=payload.requester_name,
        currency=payload.currency,
        total_amount=total,
        line_items_json=[item.model_dump() for item in payload.line_items],
    )
    db.add(po)
    await db.flush()

    validated = await validate_purchase_order(
        db, po, settings, llm_router, actor=payload.requester_name
    )
    await db.commit()
    return validated


@router.get("/orders/{po_id}", response_model=PurchaseOrderRead)
async def get_purchase_order(po_id: str, db: AsyncSession = Depends(get_db)) -> PurchaseOrderRead:
    """Retrieve a single purchase order by ID."""
    po = await db.get(PurchaseOrder, po_id)
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    vendor = await db.get(Vendor, po.vendor_id)
    return PurchaseOrderRead.model_validate(po).model_copy(
        update={"vendor_name": vendor.name if vendor else ""}
    )


@router.post("/orders/{po_id}/validate", response_model=PurchaseOrderRead)
async def revalidate_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> PurchaseOrderRead:
    """Re-run quote, budget, arithmetic, and benchmark validation on a purchase order."""
    po = await db.get(PurchaseOrder, po_id)
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    validated = await validate_purchase_order(db, po, settings, llm_router)
    await db.commit()
    return validated


@router.post("/orders/{po_id}/submit", status_code=status.HTTP_201_CREATED)
async def submit_purchase_order(
    po_id: str,
    payload: PurchaseOrderSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Submit a validated purchase order to the finance HITL approval queue."""
    approval = await submit_po_for_approval(
        db,
        po_id,
        requested_by=payload.requested_by,
        override_warnings=payload.override_warnings,
        justification=payload.justification,
    )
    await db.commit()
    return {
        "approval_id": approval.id,
        "status": approval.status,
        "required_role": approval.required_role,
    }
