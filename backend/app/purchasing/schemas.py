from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class POLineItem(BaseModel):
    sku_code: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    quantity: int
    unit_price: float
    line_total: float


class ValidationIssue(BaseModel):
    code: str
    severity: str
    message: str
    field: str = ""


class BudgetAccountCreate(BaseModel):
    cost_center_code: str = Field(min_length=2, max_length=48)
    department: str = Field(min_length=2, max_length=120)
    fiscal_year: int = Field(default=2026, ge=2020, le=2040)
    annual_budget: float = Field(gt=0.0)
    committed_amount: float = Field(default=0.0, ge=0.0)
    owner_name: str = Field(min_length=2, max_length=120)


class BudgetAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cost_center_code: str
    department: str
    fiscal_year: int
    annual_budget: float
    committed_amount: float
    remaining_budget: float = 0.0
    owner_name: str
    created_at: datetime


class VendorQuoteCreate(BaseModel):
    vendor_id: str
    quote_number: str = Field(min_length=2, max_length=80)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    valid_until: date
    total_amount: float | None = None
    line_items: list[POLineItem] = Field(min_length=1)


class VendorQuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_id: str
    vendor_name: str = ""
    quote_number: str
    currency: str
    valid_until: date
    total_amount: float
    line_items_json: list[dict[str, Any]]
    created_at: datetime


class PurchaseOrderCreate(BaseModel):
    po_number: str = Field(min_length=2, max_length=80)
    vendor_id: str
    quote_id: str | None = None
    cost_center_code: str = Field(min_length=2, max_length=48)
    requester_name: str = Field(min_length=2, max_length=120)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    total_amount: float | None = None
    line_items: list[POLineItem] = Field(default_factory=list)


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    po_number: str
    vendor_id: str
    vendor_name: str = ""
    quote_id: str | None
    cost_center_code: str
    requester_name: str
    currency: str
    total_amount: float
    line_items_json: list[dict[str, Any]]
    status: str
    validation_status: str
    validation_issues_json: list[dict[str, Any]]
    required_approver_role: str
    approval_request_id: str | None
    ai_risk_summary: str
    created_at: datetime
    updated_at: datetime


class PurchaseOrderSubmitRequest(BaseModel):
    requested_by: str = Field(min_length=2, max_length=120)
    override_warnings: bool = False
    justification: str = ""
