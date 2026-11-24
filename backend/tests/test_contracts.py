import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_contract_playbook_comparison_pair_and_hitl_approval(client: AsyncClient) -> None:
    # 1. Create vendor and custom playbook rule
    vendor_resp = await client.post(
        "/api/v1/vendors",
        json={
            "name": "Apex Analytics",
            "category": "Data & Analytics",
            "tier": "preferred",
            "annual_spend": 120000.0,
        },
    )
    assert vendor_resp.status_code == 201
    vendor_id = vendor_resp.json()["id"]

    rule_resp = await client.post(
        "/api/v1/contracts/playbooks",
        json={
            "name": "Strict Uplift Cap",
            "clause_type": "price_uplift",
            "preferred_position": "Max 4% annual renewal uplift.",
            "max_acceptable_value": 4.0,
            "severity": "critical",
        },
    )
    assert rule_resp.status_code == 201

    rules_list = await client.get("/api/v1/contracts/playbooks")
    assert rules_list.status_code == 200
    assert len(rules_list.json()) >= 1

    # 2. Ingest high-risk MSA
    high_risk_text = (
        "This Agreement shall automatically renew for successive 12-month periods unless "
        "written notice is provided 90 days prior to expiration. Customer has no termination "
        "for convenience. Fees shall increase by 9% upon each renewal. Payment is due Net 15. "
        "Vendor aggregate liability is capped at 3 months of fees paid. Customer shall indemnify "
        "Vendor for all claims. Breach notice will be given within 72 hours. Uptime target is "
        "99.5% with no service credits."
    )
    risky_resp = await client.post(
        "/api/v1/contracts",
        json={
            "vendor_id": vendor_id,
            "title": "Apex Redline Draft MSA",
            "contract_type": "MSA",
            "annual_value": 120000.0,
            "raw_text": high_risk_text,
        },
    )
    assert risky_resp.status_code == 201
    risky = risky_resp.json()
    assert risky["risk_level"] in {"high", "critical"}
    assert risky["risk_score"] >= 60
    assert risky["status"] == "redline_required"

    by_clause = {f["clause_type"]: f for f in risky["findings"]}
    assert by_clause["auto_renewal"]["status"] == "deviation"
    assert by_clause["price_uplift"]["status"] == "deviation"
    assert by_clause["liability_cap"]["status"] == "deviation"
    assert by_clause["payment_terms"]["status"] == "deviation"
    assert by_clause["termination_convenience"]["status"] == "deviation"
    assert by_clause["data_residency"]["status"] == "deviation"
    assert by_clause["indemnification"]["status"] == "deviation"
    assert by_clause["sla_uptime"]["status"] == "deviation"

    # 3. Ingest compliant MSA
    compliant_text = (
        "No automatic renewal applies; renewal requires mutual written agreement with 30 days "
        "notice. Customer may terminate for convenience on 30 days notice. Fixed rate lock with "
        "0% price increase. Payment terms are Net 45. Mutual aggregate liability cap of 12 months "
        "fees with a 24-month super-cap. Mutual indemnification applies. Executed GDPR DPA with "
        "24 hours breach notification. Uptime SLA guarantees 99.95% availability."
    )
    clean_resp = await client.post(
        "/api/v1/contracts",
        json={
            "vendor_id": vendor_id,
            "title": "Apex Counter-Proposal MSA",
            "contract_type": "MSA",
            "annual_value": 120000.0,
            "raw_text": compliant_text,
        },
    )
    assert clean_resp.status_code == 201
    clean = clean_resp.json()
    assert clean["risk_level"] == "low"
    assert clean["risk_score"] < 20
    assert clean["status"] == "in_review"

    # 4. Side-by-side pair comparison
    pair_resp = await client.post(
        "/api/v1/contracts/compare-pair",
        json={
            "left_contract_id": clean["id"],
            "right_contract_id": risky["id"],
        },
    )
    assert pair_resp.status_code == 200
    pair_data = pair_resp.json()
    assert len(pair_data["clause_diffs"]) == 8
    assert clean["title"] in pair_data["recommendation"]

    # 5. Request HITL legal approval for the risky contract and approve it
    req_resp = await client.post(
        f"/api/v1/contracts/{risky['id']}/request-approval",
        json={"requested_by": "Samira Chen", "notes": "Executive waiver requested."},
    )
    assert req_resp.status_code == 201
    approval_payload = req_resp.json()
    assert approval_payload["required_role"] == "legal_counsel"

    decide_resp = await client.post(
        f"/api/v1/governance/approvals/{approval_payload['approval_id']}/decide",
        json={
            "decision": "approved",
            "decided_by": "General Counsel",
            "decision_notes": "Accepted with side-letter.",
        },
    )
    assert decide_resp.status_code == 200
    assert decide_resp.json()["status"] == "approved"

    refreshed = await client.get(f"/api/v1/contracts/{risky['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "approved"
