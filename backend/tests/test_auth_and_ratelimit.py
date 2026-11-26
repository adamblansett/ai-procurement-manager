import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.database import init_db
from app.main import create_app


@pytest.mark.asyncio
async def test_auth_rbac_separation_of_duties_and_strict_mode(
    seeded_client: AsyncClient,
) -> None:
    # 1. Login with seeded analyst, procurement_manager, and finance_director accounts
    analyst_login = await seeded_client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@procurement.local", "password": "ProcurementDemo2026!"},
    )
    assert analyst_login.status_code == 200
    analyst_token = analyst_login.json()["access_token"]

    me_resp = await seeded_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "analyst"

    # Bad token -> 401
    bad_me = await seeded_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer malformed.token.value"},
    )
    assert bad_me.status_code == 401

    # 2. Register a custom procurement_manager user
    reg_resp = await seeded_client.post(
        "/api/v1/auth/register",
        json={
            "email": "mgr2@procurement.local",
            "full_name": "Alex Rivera",
            "password": "StrongPassword123!",
            "role": "procurement_manager",
        },
    )
    assert reg_resp.status_code == 201
    mgr_token = reg_resp.json()["access_token"]

    # 3. Find pending finance_director approval from seeded PO-2026-1002
    approvals = (await seeded_client.get("/api/v1/governance/approvals?status=pending")).json()
    po_approval = next(a for a in approvals if a["entity_type"] == "purchase_order")
    assert po_approval["required_role"] == "finance_director"

    # Analyst cannot approve -> 403
    analyst_decide = await seeded_client.post(
        f"/api/v1/governance/approvals/{po_approval['id']}/decide",
        headers={"Authorization": f"Bearer {analyst_token}"},
        json={"decision": "approved", "decided_by": "ignored", "decision_notes": "try"},
    )
    assert analyst_decide.status_code == 403

    # Procurement manager cannot approve finance_director gate -> 403
    mgr_decide = await seeded_client.post(
        f"/api/v1/governance/approvals/{po_approval['id']}/decide",
        headers={"Authorization": f"Bearer {mgr_token}"},
        json={"decision": "approved", "decided_by": "ignored", "decision_notes": "try"},
    )
    assert mgr_decide.status_code == 403

    # Separation of duties: requester (Nadia Patel) cannot approve own request
    self_approve = await seeded_client.post(
        f"/api/v1/governance/approvals/{po_approval['id']}/decide",
        json={"decision": "approved", "decided_by": "Nadia Patel", "decision_notes": "self"},
    )
    assert self_approve.status_code == 403
    assert "Separation of duties" in self_approve.json()["detail"]

    # Finance Director approves -> 200
    dir_login = await seeded_client.post(
        "/api/v1/auth/login",
        json={"email": "finance.director@procurement.local", "password": "ProcurementDemo2026!"},
    )
    dir_token = dir_login.json()["access_token"]
    dir_decide = await seeded_client.post(
        f"/api/v1/governance/approvals/{po_approval['id']}/decide",
        headers={"Authorization": f"Bearer {dir_token}"},
        json={
            "decision": "approved",
            "decided_by": "ignored",
            "decision_notes": "Verified by Finance Director.",
        },
    )
    assert dir_decide.status_code == 200
    assert dir_decide.json()["status"] == "approved"
    assert dir_decide.json()["decided_by"] == "Arthur Gomez"


@pytest.mark.asyncio
async def test_auth_required_mode_and_rate_limiter() -> None:
    strict_app = create_app(
        Settings(
            app_env="development",
            database_url="sqlite+aiosqlite:///:memory:",
            auto_seed_demo_data=False,
            auth_required=True,
            rate_limit_enabled=True,
            rate_limit_requests_per_minute=5,
        )
    )
    await init_db(strict_app.state.engine)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=strict_app), base_url="http://test"
        ) as c:
            # Public health works without token and does not burn rate-limit bucket
            for _ in range(5):
                health = await c.get("/api/v1/health")
                assert health.status_code == 200

            # Request 1: Protected endpoint rejects anonymous request (401)
            unauth = await c.get("/api/v1/vendors")
            assert unauth.status_code == 401

            # Request 2: Register gets token
            reg = await c.post(
                "/api/v1/auth/register",
                json={
                    "email": "ops@procurement.local",
                    "full_name": "Ops User",
                    "password": "Password1234!",
                    "role": "admin",
                },
            )
            assert reg.status_code == 201
            token = reg.json()["access_token"]
            hdrs = {"Authorization": f"Bearer {token}"}

            # Requests 3, 4, 5 succeed; 6th hits rate limit 429
            for _ in range(3):
                ok_resp = await c.get("/api/v1/vendors", headers=hdrs)
                assert ok_resp.status_code == 200
            throttled = await c.get("/api/v1/vendors", headers=hdrs)
            assert throttled.status_code == 429
            assert throttled.headers["retry-after"] == "60"
    finally:
        await strict_app.state.engine.dispose()


def test_production_requires_auth_required_flag() -> None:
    insecure_prod = Settings(
        app_env="production",
        auth_secret_key="prod-secret-value-at-least-32-characters-long",
        auth_required=False,
        cors_origins="https://procurement.internal",
    )
    with pytest.raises(RuntimeError, match="AUTH_REQUIRED"):
        create_app(insecure_prod)
