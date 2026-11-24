from datetime import date, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_po_validation_thresholds_quote_reconciliation_and_budget_commit(
    client: AsyncClient,
) -> None:
    # Setup vendor, benchmark, budget, and quote
    vendor = (
        await client.post(
            "/api/v1/vendors",
            json={
                "name": "Sentinel Sec",
                "category": "Security & Compliance",
                "tier": "strategic",
                "annual_spend": 100000.0,
            },
        )
    ).json()

    await client.post(
        "/api/v1/benchmarks",
        json={
            "vendor_id": vendor["id"],
            "sku_code": "SEC-NODE-LIC",
            "sku_name": "Security Node License",
            "category": "Security & Compliance",
            "unit_type": "node/year",
            "quoted_unit_price": 100.0,
            "annual_uplift_pct": 3.0,
        },
    )

    budget = (
        await client.post(
            "/api/v1/purchasing/budgets",
            json={
                "cost_center_code": "CC-SEC-900",
                "department": "Security Ops",
                "fiscal_year": 2026,
                "annual_budget": 100000.0,
                "committed_amount": 20000.0,
                "owner_name": "Nadia Patel",
            },
        )
    ).json()
    assert budget["remaining_budget"] == 80000.0

    quote = (
        await client.post(
            "/api/v1/purchasing/quotes",
            json={
                "vendor_id": vendor["id"],
                "quote_number": "QT-SEC-001",
                "valid_until": (date.today() + timedelta(days=30)).isoformat(),
                "line_items": [
                    {
                        "sku_code": "SEC-NODE-LIC",
                        "description": "Security Node License",
                        "quantity": 90,
                        "unit_price": 100.0,
                        "line_total": 9000.0,
                    }
                ],
            },
        )
    ).json()

    # 1. Valid PO within quote & budget -> pass -> submit -> approve -> committed incremented
    valid_po = (
        await client.post(
            "/api/v1/purchasing/orders",
            json={
                "po_number": "PO-VALID-01",
                "vendor_id": vendor["id"],
                "quote_id": quote["id"],
                "cost_center_code": "CC-SEC-900",
                "requester_name": "Nadia Patel",
                "line_items": [
                    {
                        "sku_code": "SEC-NODE-LIC",
                        "description": "Security Node License",
                        "quantity": 90,
                        "unit_price": 100.0,
                        "line_total": 9000.0,
                    }
                ],
            },
        )
    ).json()
    assert valid_po["validation_status"] == "pass"
    assert valid_po["status"] == "validated"
    assert valid_po["required_approver_role"] == "procurement_manager"

    sub_resp = await client.post(
        f"/api/v1/purchasing/orders/{valid_po['id']}/submit",
        json={"requested_by": "Nadia Patel", "justification": "Matches quote QT-SEC-001."},
    )
    assert sub_resp.status_code == 201
    approval_id = sub_resp.json()["approval_id"]

    dec_resp = await client.post(
        f"/api/v1/governance/approvals/{approval_id}/decide",
        json={"decision": "approved", "decided_by": "Procurement Lead", "decision_notes": "OK"},
    )
    assert dec_resp.status_code == 200

    refreshed_po = (await client.get(f"/api/v1/purchasing/orders/{valid_po['id']}")).json()
    assert refreshed_po["status"] == "approved"

    budgets_after = (await client.get("/api/v1/purchasing/budgets")).json()
    assert budgets_after[0]["committed_amount"] == 29000.0
    assert budgets_after[0]["remaining_budget"] == 71000.0

    # 2. Invalid PO: price overcharge vs quote + budget overrun -> blocked, /submit returns 422
    bad_po = (
        await client.post(
            "/api/v1/purchasing/orders",
            json={
                "po_number": "PO-BAD-02",
                "vendor_id": vendor["id"],
                "quote_id": quote["id"],
                "cost_center_code": "CC-SEC-900",
                "requester_name": "Nadia Patel",
                "line_items": [
                    {
                        "sku_code": "SEC-NODE-LIC",
                        "description": "Overcharged Security Licenses",
                        "quantity": 800,
                        "unit_price": 130.0,
                        "line_total": 104000.0,
                    }
                ],
            },
        )
    ).json()
    assert bad_po["validation_status"] == "fail"
    assert bad_po["status"] == "blocked"
    codes = {issue["code"] for issue in bad_po["validation_issues_json"]}
    assert "PRICE_OVERCHARGE" in codes
    assert "BUDGET_EXCEEDED" in codes
    assert "ABOVE_BENCHMARK" in codes

    blocked_submit = await client.post(
        f"/api/v1/purchasing/orders/{bad_po['id']}/submit",
        json={"requested_by": "Nadia Patel", "override_warnings": True},
    )
    assert blocked_submit.status_code == 422

    # 3. Escalation thresholds: >$50k -> finance_director, >$150k -> vp_finance
    await client.post(
        "/api/v1/purchasing/budgets",
        json={
            "cost_center_code": "CC-CAPEX-01",
            "department": "Cloud Capex",
            "fiscal_year": 2026,
            "annual_budget": 500000.0,
            "committed_amount": 0.0,
            "owner_name": "Arthur Gomez",
        },
    )
    director_po = (
        await client.post(
            "/api/v1/purchasing/orders",
            json={
                "po_number": "PO-DIR-03",
                "vendor_id": vendor["id"],
                "cost_center_code": "CC-CAPEX-01",
                "requester_name": "Jordan Ellis",
                "line_items": [
                    {
                        "sku_code": "CAPEX-01",
                        "description": "Director-level security suite",
                        "quantity": 1,
                        "unit_price": 65000.0,
                        "line_total": 65000.0,
                    }
                ],
            },
        )
    ).json()
    assert director_po["required_approver_role"] == "finance_director"

    vp_po = (
        await client.post(
            "/api/v1/purchasing/orders",
            json={
                "po_number": "PO-VP-04",
                "vendor_id": vendor["id"],
                "cost_center_code": "CC-CAPEX-01",
                "requester_name": "Jordan Ellis",
                "line_items": [
                    {
                        "sku_code": "CAPEX-02",
                        "description": "VP-level multi-year enterprise pack",
                        "quantity": 1,
                        "unit_price": 175000.0,
                        "line_total": 175000.0,
                    }
                ],
            },
        )
    ).json()
    assert vp_po["required_approver_role"] == "vp_finance"
