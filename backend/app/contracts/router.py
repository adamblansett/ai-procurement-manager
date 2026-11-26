from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.models import Contract, PlaybookRule
from app.contracts.schemas import (
    ClauseSearchHit,
    ClauseSearchRequest,
    ContractApprovalCreate,
    ContractCreate,
    ContractDetailRead,
    ContractPairCompareRequest,
    ContractPairComparisonRead,
    ContractRead,
    PlaybookRuleCreate,
    PlaybookRuleRead,
)
from app.contracts.service import (
    compare_contract_against_playbook,
    compare_contract_pair,
    get_contract_detail,
    request_contract_approval,
    search_contract_clauses,
)
from app.core.database import get_db
from app.core.documents import extract_text_from_upload
from app.core.governance import record_audit_event
from app.core.llm import LLMRouter, get_llm_router
from app.core.models import Vendor

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("/playbooks", response_model=list[PlaybookRuleRead])
async def list_playbook_rules(db: AsyncSession = Depends(get_db)) -> list[PlaybookRule]:
    """List commercial and legal playbook baseline rules."""
    rows = (
        (await db.execute(select(PlaybookRule).order_by(PlaybookRule.clause_type.asc())))
        .scalars()
        .all()
    )
    return list(rows)


@router.post("/playbooks", response_model=PlaybookRuleRead, status_code=status.HTTP_201_CREATED)
async def create_playbook_rule(
    payload: PlaybookRuleCreate, db: AsyncSession = Depends(get_db)
) -> PlaybookRule:
    """Create a new playbook rule for contract clause comparison."""
    rule = PlaybookRule(**payload.model_dump())
    db.add(rule)
    await db.flush()
    await record_audit_event(
        db,
        actor="legal-admin",
        action="playbook.rule_created",
        entity_type="playbook_rule",
        entity_id=rule.id,
        summary=f"Created playbook rule '{rule.name}' ({rule.clause_type}).",
    )
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("", response_model=list[ContractRead])
async def list_contracts(
    vendor_id: str | None = None,
    risk_level: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ContractRead]:
    """List vendor contracts with optional vendor or risk-level filtering."""
    stmt = select(Contract).order_by(Contract.created_at.desc())
    if vendor_id:
        stmt = stmt.where(Contract.vendor_id == vendor_id)
    if risk_level:
        stmt = stmt.where(Contract.risk_level == risk_level)
    contracts = (await db.execute(stmt)).scalars().all()

    vendor_ids = {c.vendor_id for c in contracts}
    vendor_names: dict[str, str] = {}
    if vendor_ids:
        vendors = (
            (await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))).scalars().all()
        )
        vendor_names = {v.id: v.name for v in vendors}

    return [
        ContractRead.model_validate(c).model_copy(
            update={"vendor_name": vendor_names.get(c.vendor_id, "")}
        )
        for c in contracts
    ]


@router.post("", response_model=ContractDetailRead, status_code=status.HTTP_201_CREATED)
async def ingest_contract(
    payload: ContractCreate,
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> ContractDetailRead:
    """Ingest a vendor contract and optionally execute playbook comparison immediately."""
    vendor = await db.get(Vendor, payload.vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    contract = Contract(
        vendor_id=payload.vendor_id,
        title=payload.title,
        contract_type=payload.contract_type,
        effective_date=payload.effective_date,
        expiration_date=payload.expiration_date,
        annual_value=round(payload.annual_value, 2),
        raw_text=payload.raw_text,
    )
    db.add(contract)
    await db.flush()
    await record_audit_event(
        db,
        actor="procurement-user",
        action="contract.ingested",
        entity_type="contract",
        entity_id=contract.id,
        summary=f"Ingested {contract.contract_type} '{contract.title}' for {vendor.name}.",
    )

    if payload.auto_compare:
        detail = await compare_contract_against_playbook(db, contract, llm_router)
        await db.commit()
        return detail

    await db.commit()
    return await get_contract_detail(db, contract.id)


@router.post("/upload", response_model=ContractDetailRead, status_code=status.HTTP_201_CREATED)
async def upload_contract_file(
    vendor_id: str = Form(...),
    title: str = Form(...),
    contract_type: str = Form("MSA"),
    annual_value: float = Form(0.0),
    auto_compare: bool = Form(True),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> ContractDetailRead:
    """Upload a .pdf, .docx, .txt, or .md contract, extract text, and run playbook diff."""
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    raw_bytes = await file.read()
    extracted_text, file_kind = extract_text_from_upload(file.filename or "contract.txt", raw_bytes)

    contract = Contract(
        vendor_id=vendor_id,
        title=title.strip(),
        contract_type=contract_type,
        annual_value=round(annual_value, 2),
        raw_text=extracted_text,
    )
    db.add(contract)
    await db.flush()
    await record_audit_event(
        db,
        actor="procurement-user",
        action="contract.uploaded",
        entity_type="contract",
        entity_id=contract.id,
        summary=(
            f"Uploaded {file_kind.upper()} '{contract.title}' for {vendor.name} "
            f"({len(extracted_text)} chars)."
        ),
    )

    if auto_compare:
        detail = await compare_contract_against_playbook(db, contract, llm_router)
        await db.commit()
        return detail

    await db.commit()
    return await get_contract_detail(db, contract.id)


@router.post("/search", response_model=list[ClauseSearchHit])
async def semantic_clause_search(
    payload: ClauseSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> list[ClauseSearchHit]:
    """Search across all indexed contract clauses by semantic similarity."""
    return await search_contract_clauses(db, payload)


@router.post("/compare-pair", response_model=ContractPairComparisonRead)
async def compare_two_contracts(
    payload: ContractPairCompareRequest,
    db: AsyncSession = Depends(get_db),
) -> ContractPairComparisonRead:
    """Return a side-by-side clause comparison across two ingested contracts."""
    return await compare_contract_pair(db, payload.left_contract_id, payload.right_contract_id)


@router.get("/{contract_id}", response_model=ContractDetailRead)
async def read_contract(contract_id: str, db: AsyncSession = Depends(get_db)) -> ContractDetailRead:
    """Retrieve a single contract with its clause-by-clause playbook findings."""
    return await get_contract_detail(db, contract_id)


@router.post("/{contract_id}/compare", response_model=ContractDetailRead)
async def recompare_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> ContractDetailRead:
    """Re-run playbook clause comparison on an existing contract."""
    contract = await db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    detail = await compare_contract_against_playbook(db, contract, llm_router)
    await db.commit()
    return detail


@router.post("/{contract_id}/request-approval", status_code=status.HTTP_201_CREATED)
async def submit_contract_for_approval(
    contract_id: str,
    payload: ContractApprovalCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Escalate a reviewed contract to human-in-the-loop legal or procurement approval."""
    approval = await request_contract_approval(
        db,
        contract_id,
        requested_by=payload.requested_by,
        notes=payload.notes,
    )
    await db.commit()
    return {
        "approval_id": approval.id,
        "status": approval.status,
        "required_role": approval.required_role,
    }
