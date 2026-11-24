import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.llm import LLMRequest, LLMRouter
from app.core.pii import redact_pii


def test_redact_pii_scrubs_all_sensitive_categories() -> None:
    sample = (
        "Contact jane.doe@vendorcorp.com or +1 (415) 555-0199. "
        "Tax ID: 12-3456789, SSN 123-45-6789, Account #: ACCT-99887766, "
        "Card 4111-2222-3333-4444, Host 192.168.10.42."
    )
    result = redact_pii(sample)
    assert "jane.doe@vendorcorp.com" not in result.redacted_text
    assert "415" not in result.redacted_text
    assert "12-3456789" not in result.redacted_text
    assert "123-45-6789" not in result.redacted_text
    assert "ACCT-99887766" not in result.redacted_text
    assert "4111-2222-3333-4444" not in result.redacted_text
    assert "192.168.10.42" not in result.redacted_text

    assert "[REDACTED_EMAIL]" in result.redacted_text
    assert "[REDACTED_PHONE]" in result.redacted_text
    assert "[REDACTED_TAX_ID]" in result.redacted_text
    assert "[REDACTED_SSN]" in result.redacted_text
    assert "[REDACTED_ACCOUNT]" in result.redacted_text
    assert "[REDACTED_CARD]" in result.redacted_text
    assert "[REDACTED_IP]" in result.redacted_text
    assert result.redactions_count == 7
    assert set(result.categories) == {
        "account",
        "card",
        "email",
        "ip_address",
        "phone",
        "ssn",
        "tax_id",
    }


@pytest.mark.asyncio
async def test_llm_router_mock_tasks() -> None:
    router = LLMRouter(Settings(llm_default_provider="mock"))

    contract_resp = await router.generate(
        LLMRequest(
            task="contract_compare",
            system_prompt="Review MSA",
            user_prompt="Compare clauses",
            context={
                "vendor_name": "Meridian",
                "contract_title": "Meridian MSA",
                "risk_score": 78,
                "risk_level": "critical",
                "deviations": ["price_uplift", "liability_cap"],
                "missing_clauses": [],
                "favorable_clauses": [],
            },
        )
    )
    assert contract_resp.provider == "mock"
    assert "78/100" in contract_resp.content
    assert "price_uplift" in contract_resp.content

    po_resp = await router.generate(
        LLMRequest(
            task="po_risk_summary",
            system_prompt="Validate PO",
            user_prompt="Summarize PO",
            context={
                "po_number": "PO-999",
                "vendor_name": "Vanguard",
                "total_amount": 55000.0,
                "validation_status": "warning",
                "required_approver_role": "finance_director",
                "issues": ["Unit price is 18% above benchmark median"],
            },
        )
    )
    assert "PO-999" in po_resp.content
    assert "finance director" in po_resp.content

    renewal_resp = await router.generate(
        LLMRequest(
            task="renewal_brief",
            system_prompt="Draft dossier",
            user_prompt="Build renewal brief",
            context={
                "vendor_name": "Meridian",
                "contract_title": "CRM MSA",
                "current_annual_value": 100000.0,
                "proposed_uplift_pct": 9.0,
                "projected_value": 109000.0,
                "target_value": 92000.0,
                "estimated_savings": 17000.0,
                "days_to_notice_deadline": 12,
                "leverage_points": ["9% uplift exceeds 5% policy cap"],
                "redlines": ["Reduce notice window to 30 days"],
                "draft_email": "Subject: Notice",
            },
        )
    )
    assert "$17,000.00" in renewal_resp.content
    assert "Requires HITL Approval" in renewal_resp.content


@pytest.mark.asyncio
async def test_gemini_adapter_redacts_pii_before_outbound_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_post(
        self: httpx.AsyncClient, url: str, **kwargs: Any
    ) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            status_code=200,
            request=httpx.Request("POST", url),
            json={"candidates": [{"content": {"parts": [{"text": "Clean cloud review."}]}}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    router = LLMRouter(
        Settings(
            llm_default_provider="gemini",
            llm_fallback_providers="mock",
            gemini_api_key="test-gemini-key",
            llm_redact_pii_for_cloud=True,
        )
    )

    resp = await router.generate(
        LLMRequest(
            task="contract_compare",
            system_prompt="Contact legal@acme.com if escalated.",
            user_prompt=(
                "Signer SSN 123-45-6789, Account #: ACCT-55443322, "
                "email vendor-rep@supplier.io."
            ),
        )
    )

    serialized = json.dumps(captured["json"])
    assert "legal@acme.com" not in serialized
    assert "123-45-6789" not in serialized
    assert "ACCT-55443322" not in serialized
    assert "vendor-rep@supplier.io" not in serialized
    assert "[REDACTED_EMAIL]" in serialized
    assert "[REDACTED_SSN]" in serialized
    assert "[REDACTED_ACCOUNT]" in serialized

    assert resp.provider == "gemini"
    assert resp.pii_redacted is True
    assert resp.redactions_count == 4
    assert resp.fallback_used is False


@pytest.mark.asyncio
async def test_llm_router_falls_back_to_mock_when_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_post(
        self: httpx.AsyncClient, url: str, **kwargs: Any
    ) -> httpx.Response:
        raise httpx.ConnectError("Ollama unreachable")

    monkeypatch.setattr(httpx.AsyncClient, "post", failing_post)
    router = LLMRouter(
        Settings(
            llm_default_provider="ollama",
            llm_fallback_providers="gemini,mock",
            gemini_api_key="",
        )
    )

    resp = await router.generate(
        LLMRequest(
            task="contract_compare",
            system_prompt="Review",
            user_prompt="Analyze",
            context={"vendor_name": "Acme", "contract_title": "MSA", "risk_score": 10},
        )
    )
    assert resp.provider == "mock"
    assert resp.fallback_used is True
