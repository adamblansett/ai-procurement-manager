from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.core.auth import create_access_token
from app.core.config import Settings
from app.core.governance import verify_audit_chain
from app.core.models import AuditLog
from app.main import create_app


@pytest.mark.asyncio
async def test_renewal_brief_hitl_action_and_seeded_dashboard(
    seeded_client: AsyncClient,
) -> None:
    # Seeded dashboard summary should reflect populated data
    dash_resp = await seeded_client.get("/api/v1/dashboard/summary")
    assert dash_resp.status_code == 200
    dash = dash_resp.json()
    assert dash["total_vendors"] == 5
    assert dash["active_contracts"] == 3
    assert dash["benchmarks_count"] == 12
    assert dash["pending_approvals_count"] == 2
    assert dash["blocked_pos_count"] == 1
    assert dash["urgent_renewals_count"] >= 3
    assert dash["estimated_savings_opportunity"] > 0

    # Idempotent /seed call returns seeded=0 when already populated
    reseed = await seeded_client.post("/api/v1/seed")
    assert reseed.status_code == 200
    assert reseed.json()["seeded"] == 0

    # Create a new critical renewal and generate brief
    vendors = (await seeded_client.get("/api/v1/vendors")).json()
    vendor_id = vendors[0]["id"]
    contracts = (await seeded_client.get("/api/v1/contracts")).json()
    contract_id = contracts[0]["id"]

    # Renewal date 45 days out with 30-day notice -> notice deadline 15 days out (critical)
    renewal_resp = await seeded_client.post(
        "/api/v1/renewals",
        json={
            "vendor_id": vendor_id,
            "contract_id": contract_id,
            "contract_title": "Test Critical Renewal",
            "renewal_date": (date.today() + timedelta(days=45)).isoformat(),
            "notice_period_days": 30,
            "auto_renew": True,
            "current_annual_value": 80000.0,
            "proposed_uplift_pct": 8.0,
            "owner_name": "Samira Chen",
        },
    )
    assert renewal_resp.status_code == 201
    renewal = renewal_resp.json()
    assert renewal["urgency"] == "critical"
    assert renewal["days_to_notice_deadline"] == 15

    brief_resp = await seeded_client.post(f"/api/v1/renewals/{renewal['id']}/generate-brief")
    assert brief_resp.status_code == 200
    brief = brief_resp.json()
    assert brief["projected_value"] == 86400.0
    assert brief["estimated_annual_savings"] > 0
    assert len(brief["leverage_points"]) >= 1
    assert "HITL Approval" in brief["brief_markdown"]

    # Request HITL non-renewal notice and approve
    action_resp = await seeded_client.post(
        f"/api/v1/renewals/{renewal['id']}/request-action",
        json={
            "action_type": "send_non_renewal_notice",
            "requested_by": "Samira Chen",
            "notes": "Serve protective notice ahead of 15-day deadline.",
        },
    )
    assert action_resp.status_code == 201
    approval_id = action_resp.json()["approval_id"]

    decide_resp = await seeded_client.post(
        f"/api/v1/governance/approvals/{approval_id}/decide",
        json={
            "decision": "approved",
            "decided_by": "Arthur Gomez",
            "decision_notes": "Approved protective non-renewal notice.",
        },
    )
    assert decide_resp.status_code == 200

    updated_renewal = (await seeded_client.get(f"/api/v1/renewals/{renewal['id']}")).json()
    assert updated_renewal["decision_status"] == "notice_approved"

    # Verify audit hash chain integrity across all seeded and newly created events
    verify_resp = await seeded_client.get("/api/v1/governance/audit-logs/verify")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is True
    assert verify_data["total_entries"] >= 10


@pytest.mark.asyncio
async def test_audit_chain_detects_tampering_and_seed_disabled_in_prod(
    app_instance: FastAPI,
    seeded_client: AsyncClient,
) -> None:
    # Tamper with an immutable audit row directly in DB and verify detection
    async with app_instance.state.session_factory() as db:
        await db.execute(
            update(AuditLog).where(AuditLog.sequence_num == 1).values(summary="TAMPERED ENTRY")
        )
        await db.commit()

    verify_resp = await seeded_client.get("/api/v1/governance/audit-logs/verify")
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["valid"] is False
    assert data["broken_at_sequence"] == 1

    async with app_instance.state.session_factory() as db:
        direct = await verify_audit_chain(db)
        assert direct["valid"] is False

    # Verify /seed is blocked in production mode even when authenticated
    prod_settings = Settings(
        app_env="production",
        auth_secret_key="prod-secret-value-at-least-32-characters-long",
        auth_required=True,
        cors_origins="https://procurement.internal",
        database_url="sqlite+aiosqlite:///:memory:",
        auto_seed_demo_data=False,
    )
    prod_app = create_app(prod_settings)
    prod_token = create_access_token(
        user_id="u-prod",
        email="admin@procurement.internal",
        full_name="Prod Admin",
        role="admin",
        settings=prod_settings,
    )
    async with AsyncClient(
        transport=ASGITransport(app=prod_app), base_url="http://test"
    ) as prod_client:
        prod_seed = await prod_client.post(
            "/api/v1/seed", headers={"Authorization": f"Bearer {prod_token}"}
        )
        assert prod_seed.status_code == 403
    await prod_app.state.engine.dispose()
