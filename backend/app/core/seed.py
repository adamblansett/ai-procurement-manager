from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.benchmarks.models import PricingBenchmark
from app.contracts.models import Contract, PlaybookRule
from app.contracts.service import (
    DEFAULT_PLAYBOOK_SPECS,
    compare_contract_against_playbook,
    request_contract_approval,
)
from app.core.auth import hash_password
from app.core.config import Settings
from app.core.governance import record_audit_event
from app.core.llm import LLMRouter
from app.core.models import ApprovalRequest, User, Vendor
from app.purchasing.models import BudgetAccount, PurchaseOrder, VendorQuote
from app.purchasing.service import submit_po_for_approval, validate_purchase_order
from app.renewals.alerts import run_renewal_alert_sweep
from app.renewals.models import RenewalItem
from app.renewals.service import generate_renegotiation_brief

DEMO_USERS: tuple[tuple[str, str, str], ...] = (
    ("admin@procurement.local", "Morgan Blake", "admin"),
    ("vp.finance@procurement.local", "Evelyn Shaw", "vp_finance"),
    ("finance.director@procurement.local", "Arthur Gomez", "finance_director"),
    ("legal.counsel@procurement.local", "Diana Morales", "legal_counsel"),
    ("procurement.mgr@procurement.local", "Samira Chen", "procurement_manager"),
    ("analyst@procurement.local", "Nadia Patel", "analyst"),
)


async def ensure_demo_users(db: AsyncSession) -> int:
    """Idempotently seed baseline RBAC user accounts for local testing."""
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if user_count > 0:
        return 0
    default_hash = hash_password("ProcurementDemo2026!")
    for email, full_name, role in DEMO_USERS:
        db.add(
            User(
                email=email,
                full_name=full_name,
                role=role,
                password_hash=default_hash,
                is_active=True,
            )
        )
    await db.flush()
    return len(DEMO_USERS)


async def seed_demo_data(
    session_factory: async_sessionmaker[AsyncSession],
    llm_router: LLMRouter,
    settings: Settings | None = None,
) -> dict[str, int]:
    """Idempotently populate realistic enterprise procurement records for local evaluation."""
    cfg = settings or llm_router.settings
    async with session_factory() as db:
        users_seeded = await ensure_demo_users(db)
        existing_count = (await db.execute(select(func.count()).select_from(Vendor))).scalar_one()
        if existing_count > 0:
            if users_seeded > 0:
                await db.commit()
            return {
                "seeded": 0,
                "users": users_seeded,
                "vendors": int(existing_count),
                "contracts": 0,
                "benchmarks": 0,
                "purchase_orders": 0,
                "renewals": 0,
            }

        # 1. Vendors
        vendors = [
            Vendor(
                name="Obsidian Cloud Infrastructure",
                category="Cloud & Infrastructure",
                tier="strategic",
                status="active",
                primary_contact_name="Elena Vance",
                primary_contact_email="elena.vance@obsidiancloud.example",
                annual_spend=320000.0,
                risk_score=18,
                payment_terms_days=45,
                notes="Primary Kubernetes & observability cloud platform.",
            ),
            Vendor(
                name="Meridian RevOps CRM",
                category="SaaS Applications",
                tier="preferred",
                status="under_review",
                primary_contact_name="Marcus Sterling",
                primary_contact_email="m.sterling@meridianrev.example",
                annual_spend=144000.0,
                risk_score=64,
                payment_terms_days=15,
                notes="Commercial renewal flagged for aggressive 9% uplift and 90-day auto-renew.",
            ),
            Vendor(
                name="Vanguard Cyber Defense",
                category="Security & Compliance",
                tier="strategic",
                status="active",
                primary_contact_name="Priya Nair",
                primary_contact_email="priya.nair@vanguardcyber.example",
                annual_spend=185000.0,
                risk_score=28,
                payment_terms_days=30,
                notes="Enterprise EDR & SOC telemetry vendor.",
            ),
            Vendor(
                name="Atlas Data Warehouse",
                category="Data & Analytics",
                tier="preferred",
                status="active",
                primary_contact_name="David Kim",
                primary_contact_email="dkim@atlasdw.example",
                annual_spend=210000.0,
                risk_score=22,
                payment_terms_days=45,
                notes="Snowflake-compatible analytics engine with volume tier discounts.",
            ),
            Vendor(
                name="Northstar Talent Systems",
                category="HR & Operations",
                tier="standard",
                status="active",
                primary_contact_name="Claire Brooks",
                primary_contact_email="cbrooks@northstarhr.example",
                annual_spend=68000.0,
                risk_score=34,
                payment_terms_days=30,
                notes="ATS and onboarding workflow SaaS.",
            ),
        ]
        db.add_all(vendors)
        await db.flush()
        v_cloud, v_crm, v_sec, v_data, v_hr = vendors

        # 2. Playbook Rules
        rules: list[PlaybookRule] = []
        for spec in DEFAULT_PLAYBOOK_SPECS:
            raw_max = spec.get("max_acceptable_value")
            max_val = float(raw_max) if isinstance(raw_max, int | float) else None
            rules.append(
                PlaybookRule(
                    name=str(spec["name"]),
                    clause_type=str(spec["clause_type"]),
                    preferred_position=str(spec["preferred_position"]),
                    fallback_position=str(spec["fallback_position"]),
                    max_acceptable_value=max_val,
                    severity=str(spec["severity"]),
                    guidance=str(spec["guidance"]),
                    is_active=True,
                )
            )
        db.add_all(rules)
        await db.flush()

        # 3. Contracts (3 realistic contracts with varied risk profiles)
        today = date.today()
        c_crm = Contract(
            vendor_id=v_crm.id,
            title="Meridian RevOps Master Subscription Agreement",
            contract_type="MSA",
            effective_date=today - timedelta(days=290),
            expiration_date=today + timedelta(days=72),
            annual_value=144000.0,
            raw_text=(
                "Section 4. Term & Renewal: This Agreement shall automatically renew for "
                "successive 12-month periods unless Customer provides written non-renewal "
                "notice at least 90 days prior to expiration. There is no termination for "
                "convenience during a committed term.\n"
                "Section 5. Pricing Uplift: Renewal fees shall increase by 9% annually "
                "upon each renewal.\n"
                "Section 6. Payment: Invoices are payable Net 15 from invoice date.\n"
                "Section 8. Limitation of Liability: Vendor's aggregate liability shall "
                "not exceed 3 months of fees paid prior to the claim.\n"
                "Section 9. Indemnification: Customer shall indemnify Vendor from "
                "third-party usage claims.\n"
                "Section 10. Security & SLA: Breach notice shall be provided within "
                "72 hours. Target uptime availability is 99.5% with no service credits."
            ),
        )
        c_cloud = Contract(
            vendor_id=v_cloud.id,
            title="Obsidian Cloud Enterprise MSA & DPA",
            contract_type="MSA",
            effective_date=today - timedelta(days=210),
            expiration_date=today + timedelta(days=155),
            annual_value=320000.0,
            raw_text=(
                "Section 3. Renewal: No automatic renewal applies; renewal requires "
                "mutual written agreement with 30 days notice. Customer may terminate "
                "for convenience on 30 days written notice.\n"
                "Section 4. Pricing: Fixed rate lock with 0% price increase for 36 months.\n"
                "Section 5. Payment Terms: Net 45 from receipt of undisputed invoice.\n"
                "Section 7. Liability Cap: Mutual aggregate liability cap of 12 months "
                "fees with a 24-month super-cap for data breach and IP indemnity.\n"
                "Section 8. Mutual Indemnification: Mutual indemnification applies "
                "including uncapped vendor IP defense.\n"
                "Section 9. Data Residency & SLA: Executed GDPR DPA with SOC 2 Type II "
                "controls and 24 hours breach notification. Uptime SLA guarantees 99.95% "
                "availability with tiered service credits."
            ),
        )
        c_sec = Contract(
            vendor_id=v_sec.id,
            title="Vanguard Cyber Defense Enterprise Order & DPA",
            contract_type="DPA",
            effective_date=today - timedelta(days=260),
            expiration_date=today + timedelta(days=105),
            annual_value=185000.0,
            raw_text=(
                "Section 2. Renewal: Agreement automatically renews unless notice is "
                "given 60 days prior to term end; Customer may terminate for convenience "
                "on 60 days notice.\n"
                "Section 3. Pricing Uplift: Annual price uplift capped at 4.0% upon renewal.\n"
                "Section 4. Payment Terms: Net 30 from receipt of invoice.\n"
                "Section 6. Liability: Aggregate liability capped at 12 months of fees paid.\n"
                "Section 7. Indemnification: Mutual indemnification for third-party IP "
                "infringement claims.\n"
                "Section 8. DPA & SLA: Executed DPA with US/EU data residency and 36 hours "
                "security breach notice. Uptime SLA is 99.9% monthly availability."
            ),
        )
        db.add_all([c_crm, c_cloud, c_sec])
        await db.flush()

        for contract in (c_crm, c_cloud, c_sec):
            await compare_contract_against_playbook(
                db, contract, llm_router, actor="seed-bootstrap"
            )

        # 4. Normalized Pricing Benchmarks (12 records across 5 SKUs)
        benchmarks = [
            PricingBenchmark(
                vendor_id=v_crm.id,
                sku_code="CRM-ENT-SEAT",
                sku_name="Enterprise Revenue CRM Seat",
                category="SaaS Applications",
                unit_type="seat/month",
                volume_tier="51-250",
                quoted_unit_price=125.0,
                annual_uplift_pct=3.0,
                discount_pct=18.0,
                source="executed_contract",
                effective_year=2025,
                notes="Peer benchmark cohort (150 seats).",
            ),
            PricingBenchmark(
                vendor_id=v_crm.id,
                sku_code="CRM-ENT-SEAT",
                sku_name="Enterprise Revenue CRM Seat",
                category="SaaS Applications",
                unit_type="seat/month",
                volume_tier="51-250",
                quoted_unit_price=140.0,
                annual_uplift_pct=4.0,
                discount_pct=12.0,
                source="historical_quote",
                effective_year=2026,
                notes="Standard mid-market CRM quote.",
            ),
            PricingBenchmark(
                vendor_id=None,
                sku_code="CRM-ENT-SEAT",
                sku_name="Enterprise Revenue CRM Seat",
                category="SaaS Applications",
                unit_type="seat/month",
                volume_tier="251-1000",
                quoted_unit_price=112.0,
                annual_uplift_pct=2.5,
                discount_pct=24.0,
                source="market_index",
                effective_year=2026,
                notes="Multi-year Q4 volume benchmark.",
            ),
            PricingBenchmark(
                vendor_id=v_sec.id,
                sku_code="VGD-EDR-PRO",
                sku_name="Endpoint Detection & Telemetry License",
                category="Security & Compliance",
                unit_type="endpoint/year",
                volume_tier="251-1000",
                quoted_unit_price=175.0,
                annual_uplift_pct=3.0,
                discount_pct=22.0,
                source="executed_contract",
                effective_year=2025,
                notes="Prior year executed tier rate.",
            ),
            PricingBenchmark(
                vendor_id=v_sec.id,
                sku_code="VGD-EDR-PRO",
                sku_name="Endpoint Detection & Telemetry License",
                category="Security & Compliance",
                unit_type="endpoint/year",
                volume_tier="251-1000",
                quoted_unit_price=190.0,
                annual_uplift_pct=3.5,
                discount_pct=15.0,
                source="historical_quote",
                effective_year=2026,
                notes="Q1 security peer cohort.",
            ),
            PricingBenchmark(
                vendor_id=None,
                sku_code="VGD-EDR-PRO",
                sku_name="Endpoint Detection & Telemetry License",
                category="Security & Compliance",
                unit_type="endpoint/year",
                volume_tier="251-1000",
                quoted_unit_price=205.0,
                annual_uplift_pct=4.0,
                discount_pct=10.0,
                source="market_index",
                effective_year=2026,
                notes="Market index upper quartile.",
            ),
            PricingBenchmark(
                vendor_id=v_cloud.id,
                sku_code="CLD-K8S-NODE",
                sku_name="Managed Compute Cluster Pack",
                category="Cloud & Infrastructure",
                unit_type="cluster/month",
                volume_tier="1-50",
                quoted_unit_price=3400.0,
                annual_uplift_pct=0.0,
                discount_pct=20.0,
                source="executed_contract",
                effective_year=2026,
                notes="3-year committed spend rate.",
            ),
            PricingBenchmark(
                vendor_id=v_cloud.id,
                sku_code="CLD-K8S-NODE",
                sku_name="Managed Compute Cluster Pack",
                category="Cloud & Infrastructure",
                unit_type="cluster/month",
                volume_tier="1-50",
                quoted_unit_price=3650.0,
                annual_uplift_pct=2.0,
                discount_pct=14.0,
                source="historical_quote",
                effective_year=2026,
                notes="Standard annual commit quote.",
            ),
            PricingBenchmark(
                vendor_id=v_data.id,
                sku_code="DATA-WH-CREDIT",
                sku_name="Analytics Compute Credit Pack",
                category="Data & Analytics",
                unit_type="pack/year",
                volume_tier="51-250",
                quoted_unit_price=2100.0,
                annual_uplift_pct=2.0,
                discount_pct=16.0,
                source="executed_contract",
                effective_year=2025,
                notes="Committed capacity rate.",
            ),
            PricingBenchmark(
                vendor_id=v_data.id,
                sku_code="DATA-WH-CREDIT",
                sku_name="Analytics Compute Credit Pack",
                category="Data & Analytics",
                unit_type="pack/year",
                volume_tier="51-250",
                quoted_unit_price=2280.0,
                annual_uplift_pct=3.0,
                discount_pct=11.0,
                source="market_index",
                effective_year=2026,
                notes="Market median credit pack.",
            ),
            PricingBenchmark(
                vendor_id=v_hr.id,
                sku_code="HR-ATS-SEAT",
                sku_name="Recruiting & Onboarding Suite",
                category="HR & Operations",
                unit_type="seat/year",
                volume_tier="51-250",
                quoted_unit_price=310.0,
                annual_uplift_pct=3.0,
                discount_pct=14.0,
                source="executed_contract",
                effective_year=2026,
                notes="Annual ATS seat rate.",
            ),
            PricingBenchmark(
                vendor_id=v_hr.id,
                sku_code="HR-ATS-SEAT",
                sku_name="Recruiting & Onboarding Suite",
                category="HR & Operations",
                unit_type="seat/year",
                volume_tier="51-250",
                quoted_unit_price=345.0,
                annual_uplift_pct=4.5,
                discount_pct=8.0,
                source="historical_quote",
                effective_year=2026,
                notes="Unnegotiated list-minus quote.",
            ),
        ]
        db.add_all(benchmarks)
        await db.flush()

        # 5. Budgets
        budgets = [
            BudgetAccount(
                cost_center_code="CC-ENG-401",
                department="Engineering Platform",
                fiscal_year=2026,
                annual_budget=480000.0,
                committed_amount=185000.0,
                owner_name="Jordan Ellis (VP Engineering)",
            ),
            BudgetAccount(
                cost_center_code="CC-SEC-204",
                department="Information Security",
                fiscal_year=2026,
                annual_budget=220000.0,
                committed_amount=95000.0,
                owner_name="Nadia Patel (CISO)",
            ),
            BudgetAccount(
                cost_center_code="CC-REV-310",
                department="Revenue Operations",
                fiscal_year=2026,
                annual_budget=210000.0,
                committed_amount=192000.0,
                owner_name="Samira Chen (VP RevOps)",
            ),
            BudgetAccount(
                cost_center_code="CC-FIN-105",
                department="Finance & Procurement",
                fiscal_year=2026,
                annual_budget=120000.0,
                committed_amount=30000.0,
                owner_name="Arthur Gomez (Controller)",
            ),
        ]
        db.add_all(budgets)
        await db.flush()

        # 6. Vendor Quotes
        q_cloud = VendorQuote(
            vendor_id=v_cloud.id,
            quote_number="QT-OBS-882",
            valid_until=today + timedelta(days=45),
            total_amount=42000.0,
            line_items_json=[
                {
                    "sku_code": "CLD-K8S-NODE",
                    "description": "Managed Compute Cluster Pack (12-mo expansion)",
                    "quantity": 12,
                    "unit_price": 3500.0,
                    "line_total": 42000.0,
                }
            ],
        )
        q_sec = VendorQuote(
            vendor_id=v_sec.id,
            quote_number="QT-VGD-419",
            valid_until=today + timedelta(days=30),
            total_amount=62500.0,
            line_items_json=[
                {
                    "sku_code": "VGD-EDR-PRO",
                    "description": "Enterprise EDR & Telemetry Annual Licenses",
                    "quantity": 250,
                    "unit_price": 250.0,
                    "line_total": 62500.0,
                }
            ],
        )
        q_crm = VendorQuote(
            vendor_id=v_crm.id,
            quote_number="QT-MER-509",
            valid_until=today + timedelta(days=20),
            total_amount=29000.0,
            line_items_json=[
                {
                    "sku_code": "CRM-ENT-SEAT",
                    "description": "Enterprise Revenue CRM Seats (Q4 Co-term)",
                    "quantity": 200,
                    "unit_price": 145.0,
                    "line_total": 29000.0,
                }
            ],
        )
        db.add_all([q_cloud, q_sec, q_crm])
        await db.flush()

        # 7. Purchase Orders (1 approved, 1 pending HITL approval with benchmark warning, 1 blocked)
        po_approved = PurchaseOrder(
            po_number="PO-2026-1001",
            vendor_id=v_cloud.id,
            quote_id=q_cloud.id,
            cost_center_code="CC-ENG-401",
            requester_name="Jordan Ellis",
            total_amount=42000.0,
            line_items_json=q_cloud.line_items_json,
        )
        po_pending = PurchaseOrder(
            po_number="PO-2026-1002",
            vendor_id=v_sec.id,
            quote_id=q_sec.id,
            cost_center_code="CC-SEC-204",
            requester_name="Nadia Patel",
            total_amount=62500.0,
            line_items_json=q_sec.line_items_json,
        )
        po_blocked = PurchaseOrder(
            po_number="PO-2026-1003",
            vendor_id=v_crm.id,
            quote_id=q_crm.id,
            cost_center_code="CC-REV-310",
            requester_name="Samira Chen",
            total_amount=39000.0,
            line_items_json=[
                {
                    "sku_code": "CRM-ENT-SEAT",
                    "description": "Enterprise Revenue CRM Seats (Unapproved Uplift)",
                    "quantity": 200,
                    "unit_price": 195.0,
                    "line_total": 39000.0,
                }
            ],
        )
        db.add_all([po_approved, po_pending, po_blocked])
        await db.flush()

        for po in (po_approved, po_pending, po_blocked):
            await validate_purchase_order(db, po, cfg, llm_router, actor="seed-bootstrap")

        # Approve PO-2026-1001 via full HITL governance flow
        po1_approval = await submit_po_for_approval(
            db, po_approved.id, requested_by="Jordan Ellis", justification="Matched quoted rate."
        )
        po1_approval.status = "approved"
        po1_approval.decided_by = "Arthur Gomez"
        po1_approval.decision_notes = "Verified against QT-OBS-882 and ENG Q4 budget."
        po1_approval.decided_at = po1_approval.created_at
        po_approved.status = "approved"
        budgets[0].committed_amount = round(
            budgets[0].committed_amount + po_approved.total_amount, 2
        )
        await record_audit_event(
            db,
            actor="Arthur Gomez",
            action="approval.approved",
            entity_type="purchase_order",
            entity_id=po_approved.id,
            summary=f"APPROVED 'PO Approval: {po_approved.po_number}' ($42,000.00).",
            metadata={"approval_id": po1_approval.id},
        )

        # Leave PO-2026-1002 in pending_approval for finance_director review
        await submit_po_for_approval(
            db,
            po_pending.id,
            requested_by="Nadia Patel",
            override_warnings=True,
            justification="Q4 SOC audit expansion requires immediate endpoint coverage.",
        )

        # Queue 2nd pending HITL approval: High-Risk Contract Legal Review for Meridian RevOps
        await request_contract_approval(
            db,
            c_crm.id,
            requested_by="Samira Chen",
            notes="Vendor refuses liability cap increase without executive escalation.",
        )

        # 8. Renewal Items (relative to date.today() so urgency bands stay crisp)
        r_crm = RenewalItem(
            vendor_id=v_crm.id,
            contract_id=c_crm.id,
            contract_title="Meridian RevOps Enterprise License",
            renewal_date=today + timedelta(days=72),
            notice_period_days=60,
            notice_deadline=today + timedelta(days=12),
            auto_renew=True,
            current_annual_value=144000.0,
            proposed_uplift_pct=9.0,
            owner_name="Samira Chen",
            decision_status="renegotiating",
        )
        r_sec = RenewalItem(
            vendor_id=v_sec.id,
            contract_id=c_sec.id,
            contract_title="Vanguard Cyber Defense Annual Order",
            renewal_date=today + timedelta(days=102),
            notice_period_days=60,
            notice_deadline=today + timedelta(days=42),
            auto_renew=True,
            current_annual_value=185000.0,
            proposed_uplift_pct=6.5,
            owner_name="Nadia Patel",
            decision_status="monitoring",
        )
        r_data = RenewalItem(
            vendor_id=v_data.id,
            contract_id=None,
            contract_title="Atlas Data Warehouse Capacity Commit",
            renewal_date=today + timedelta(days=98),
            notice_period_days=30,
            notice_deadline=today + timedelta(days=68),
            auto_renew=True,
            current_annual_value=210000.0,
            proposed_uplift_pct=4.5,
            owner_name="Jordan Ellis",
            decision_status="monitoring",
        )
        r_cloud = RenewalItem(
            vendor_id=v_cloud.id,
            contract_id=c_cloud.id,
            contract_title="Obsidian Cloud Infrastructure Multi-Year MSA",
            renewal_date=today + timedelta(days=175),
            notice_period_days=30,
            notice_deadline=today + timedelta(days=145),
            auto_renew=False,
            current_annual_value=320000.0,
            proposed_uplift_pct=0.0,
            owner_name="Jordan Ellis",
            decision_status="monitoring",
        )
        db.add_all([r_crm, r_sec, r_data, r_cloud])
        await db.flush()

        # Pre-generate AI Renegotiation Brief for the critical Meridian RevOps renewal
        await generate_renegotiation_brief(db, r_crm.id, llm_router, actor="seed-bootstrap")
        # Run initial renewal notice alert sweep
        await run_renewal_alert_sweep(db, cfg, actor="seed-bootstrap")

        await db.commit()
        pending_count = (
            await db.execute(
                select(func.count())
                .select_from(ApprovalRequest)
                .where(ApprovalRequest.status == "pending")
            )
        ).scalar_one()
        return {
            "seeded": 1,
            "users": users_seeded,
            "vendors": len(vendors),
            "contracts": 3,
            "benchmarks": len(benchmarks),
            "purchase_orders": 3,
            "renewals": 4,
            "pending_approvals": int(pending_count),
        }
