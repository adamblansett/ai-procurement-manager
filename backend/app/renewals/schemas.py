from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RenewalCreate(BaseModel):
    vendor_id: str
    contract_id: str | None = None
    contract_title: str = Field(min_length=2, max_length=200)
    renewal_date: date
    notice_period_days: int = Field(default=60, ge=0, le=365)
    auto_renew: bool = True
    current_annual_value: float = Field(gt=0.0)
    proposed_uplift_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    owner_name: str = Field(min_length=2, max_length=120)


class RenewalUpdate(BaseModel):
    renewal_date: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    auto_renew: bool | None = None
    current_annual_value: float | None = Field(default=None, gt=0.0)
    proposed_uplift_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    owner_name: str | None = None
    decision_status: (
        Literal[
            "monitoring",
            "renegotiating",
            "notice_pending_approval",
            "notice_approved",
            "renewed",
            "non_renewing",
        ]
        | None
    ) = None


class RenewalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_id: str
    vendor_name: str = ""
    contract_id: str | None
    contract_title: str
    renewal_date: date
    notice_period_days: int
    notice_deadline: date
    days_to_notice_deadline: int = 0
    urgency: str = "healthy"
    auto_renew: bool
    current_annual_value: float
    proposed_uplift_pct: float
    projected_renewal_value: float = 0.0
    owner_name: str
    decision_status: str
    brief_markdown: str
    brief_data_json: dict[str, Any]
    brief_generated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RenewalBriefResponse(BaseModel):
    renewal: RenewalRead
    projected_value: float
    target_value: float
    estimated_annual_savings: float
    three_year_savings: float
    leverage_points: list[str]
    clause_redlines: list[str]
    recommended_timeline: list[str]
    draft_notice_email: str
    brief_markdown: str


class RenewalActionRequest(BaseModel):
    action_type: Literal[
        "send_non_renewal_notice",
        "approve_renewal_terms",
        "request_renegotiation",
    ]
    requested_by: str = Field(min_length=2, max_length=120)
    notes: str = ""
