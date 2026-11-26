from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlaybookRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    clause_type: str = Field(min_length=2, max_length=64)
    preferred_position: str = Field(min_length=4)
    fallback_position: str = ""
    max_acceptable_value: float | None = None
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    guidance: str = ""
    is_active: bool = True


class PlaybookRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    clause_type: str
    preferred_position: str
    fallback_position: str
    max_acceptable_value: float | None
    severity: str
    guidance: str
    is_active: bool
    created_at: datetime


class ContractCreate(BaseModel):
    vendor_id: str
    title: str = Field(min_length=2, max_length=200)
    contract_type: Literal["MSA", "DPA", "Order Form", "SOW"] = "MSA"
    effective_date: date | None = None
    expiration_date: date | None = None
    annual_value: float = Field(default=0.0, ge=0.0)
    raw_text: str = Field(min_length=10)
    auto_compare: bool = True


class ContractClauseFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    clause_type: str
    status: str
    severity: str
    vendor_excerpt: str
    playbook_position: str
    redline_suggestion: str
    deviation_score: int
    created_at: datetime


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_id: str
    vendor_name: str = ""
    title: str
    contract_type: str
    effective_date: date | None
    expiration_date: date | None
    annual_value: float
    raw_text: str
    status: str
    risk_score: int
    risk_level: str
    comparison_summary: str
    llm_provider_used: str
    pii_redacted: bool
    last_compared_at: datetime | None
    created_at: datetime


class ContractDetailRead(ContractRead):
    findings: list[ContractClauseFindingRead] = Field(default_factory=list)


class ContractPairCompareRequest(BaseModel):
    left_contract_id: str
    right_contract_id: str


class ClausePairDiffItem(BaseModel):
    clause_type: str
    left_status: str
    left_severity: str
    left_excerpt: str
    right_status: str
    right_severity: str
    right_excerpt: str
    delta_summary: str


class ContractPairComparisonRead(BaseModel):
    left_contract: ContractRead
    right_contract: ContractRead
    clause_diffs: list[ClausePairDiffItem]
    recommendation: str


class ContractApprovalCreate(BaseModel):
    requested_by: str = Field(min_length=2, max_length=120)
    notes: str = ""


class ClauseSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    clause_type: str | None = None
    vendor_id: str | None = None
    top_k: int = Field(default=8, ge=1, le=25)


class ClauseSearchHit(BaseModel):
    contract_id: str
    contract_title: str
    vendor_id: str
    vendor_name: str
    clause_type: str
    status: str
    risk_level: str
    chunk_text: str
    similarity_score: float
