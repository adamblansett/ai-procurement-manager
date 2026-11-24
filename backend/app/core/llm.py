from typing import Any

import httpx
import structlog
from fastapi import Request
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.pii import redact_pii

logger = structlog.get_logger(__name__)


class LLMRequest(BaseModel):
    """Structured prompt payload passed to the local-first LLM router."""

    task: str
    system_prompt: str
    user_prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Normalized LLM output with provenance and PII redaction telemetry."""

    provider: str
    model: str
    content: str
    pii_redacted: bool = False
    redactions_count: int = 0
    fallback_used: bool = False


class LLMRouter:
    """Routes AI synthesis requests across mock, local Ollama, and guarded cloud Gemini."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _provider_chain(self) -> list[str]:
        chain: list[str] = [self.settings.llm_default_provider.strip().lower()]
        for candidate in self.settings.fallback_provider_list:
            if candidate not in chain:
                chain.append(candidate)
        if "mock" not in chain:
            chain.append("mock")
        return chain

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Execute an LLM request with deterministic fallback when upstream providers fail."""
        chain = self._provider_chain()
        last_error: Exception | None = None

        for idx, provider in enumerate(chain):
            fallback_used = idx > 0
            try:
                if provider == "mock":
                    response = self._call_mock(request)
                elif provider == "ollama":
                    response = await self._call_ollama(request)
                elif provider == "gemini":
                    response = await self._call_gemini(request)
                else:
                    raise ValueError(f"Unsupported LLM provider: {provider}")
                response.fallback_used = fallback_used
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "llm_provider_failed",
                    provider=provider,
                    task=request.task,
                    error=str(exc),
                )

        raise RuntimeError(f"All LLM providers failed for task '{request.task}': {last_error}")

    async def _call_ollama(self, request: LLMRequest) -> LLMResponse:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.settings.ollama_default_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = str(data.get("message", {}).get("content", "")).strip()
        if not content:
            raise ValueError("Ollama returned an empty completion")
        return LLMResponse(
            provider="ollama",
            model=self.settings.ollama_default_model,
            content=content,
            pii_redacted=False,
            redactions_count=0,
        )

    async def _call_gemini(self, request: LLMRequest) -> LLMResponse:
        if not self.settings.gemini_api_key.strip():
            raise RuntimeError("GEMINI_API_KEY is not configured")

        system_prompt = request.system_prompt
        user_prompt = request.user_prompt
        pii_redacted = False
        redactions_count = 0

        if self.settings.llm_redact_pii_for_cloud:
            sys_result = redact_pii(system_prompt)
            usr_result = redact_pii(user_prompt)
            system_prompt = sys_result.redacted_text
            user_prompt = usr_result.redacted_text
            pii_redacted = True
            redactions_count = sys_result.redactions_count + usr_result.redactions_count

        model = self.settings.gemini_default_model
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self.settings.gemini_api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        }
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        content = "".join(str(part.get("text", "")) for part in parts).strip()
        if not content:
            raise ValueError("Gemini returned an empty completion")

        return LLMResponse(
            provider="gemini",
            model=model,
            content=content,
            pii_redacted=pii_redacted,
            redactions_count=redactions_count,
        )

    def _call_mock(self, request: LLMRequest) -> LLMResponse:
        ctx = request.context
        if request.task == "contract_compare":
            vendor_name = str(ctx.get("vendor_name", "Vendor"))
            title = str(ctx.get("contract_title", "Agreement"))
            risk_score = int(ctx.get("risk_score", 0))
            risk_level = str(ctx.get("risk_level", "low")).upper()
            deviations = list(ctx.get("deviations", []))
            missing = list(ctx.get("missing_clauses", []))
            favorable = list(ctx.get("favorable_clauses", []))

            if deviations or missing:
                flagged = ", ".join(deviations[:4]) or "none"
                missing_str = ", ".join(missing[:3]) or "none"
                content = (
                    f"{title} ({vendor_name}) scored {risk_score}/100 ({risk_level} risk). "
                    f"Key playbook deviations detected in: {flagged}. "
                    f"Missing clauses: {missing_str}. "
                    f"Favorable positions: {', '.join(favorable) if favorable else 'standard'}. "
                    "Recommend legal/commercial redlines before signature or renewal lock-in."
                )
            else:
                content = (
                    f"{title} ({vendor_name}) scored {risk_score}/100 ({risk_level} risk). "
                    "All evaluated commercial and security clauses align with playbook standards "
                    "and are ready for standard procurement sign-off."
                )
        elif request.task == "po_risk_summary":
            po_number = str(ctx.get("po_number", "PO"))
            vendor_name = str(ctx.get("vendor_name", "Vendor"))
            total_amount = float(ctx.get("total_amount", 0.0))
            validation_status = str(ctx.get("validation_status", "pass")).upper()
            role = str(ctx.get("required_approver_role", "procurement_manager")).replace("_", " ")
            issues = list(ctx.get("issues", []))
            if issues:
                summary_issues = "; ".join(str(item) for item in issues[:3])
                content = (
                    f"{po_number} for {vendor_name} (${total_amount:,.2f}) finished validation "
                    f"with status {validation_status}. Findings: {summary_issues}. "
                    f"Routing requires {role} review."
                )
            else:
                content = (
                    f"{po_number} for {vendor_name} (${total_amount:,.2f}) passed all quote, "
                    f"line-item arithmetic, budget-headroom, and benchmark checks. "
                    f"Eligible for {role} approval."
                )
        elif request.task == "renewal_brief":
            vendor_name = str(ctx.get("vendor_name", "Vendor"))
            contract_title = str(ctx.get("contract_title", "Subscription Agreement"))
            current_val = float(ctx.get("current_annual_value", 0.0))
            uplift = float(ctx.get("proposed_uplift_pct", 0.0))
            projected = float(ctx.get("projected_value", current_val))
            target = float(ctx.get("target_value", current_val))
            savings = float(ctx.get("estimated_savings", 0.0))
            days_left = int(ctx.get("days_to_notice_deadline", 0))
            leverage = list(ctx.get("leverage_points", []))
            redlines = list(ctx.get("redlines", []))
            draft_email = str(ctx.get("draft_email", ""))

            leverage_md = (
                "\n".join(f"- {point}" for point in leverage) or "- Multi-year flat-rate commitment"
            )
            redline_md = (
                "\n".join(f"- {item}" for item in redlines)
                or "- Cap renewal uplift at <=3% and shorten notice window to 30 days"
            )
            content = (
                f"## Renegotiation Dossier: {vendor_name} — {contract_title}\n\n"
                f"- **Days to Notice Deadline:** {days_left} days\n"
                f"- **Current Annual Value:** ${current_val:,.2f} "
                f"(Proposed uplift: {uplift:.1f}% -> ${projected:,.2f})\n"
                f"- **Target Renewal Value:** ${target:,.2f} "
                f"(**Estimated Annual Savings:** ${savings:,.2f})\n\n"
                f"### Commercial & Pricing Leverage\n{leverage_md}\n\n"
                f"### Recommended Contract Redlines\n{redline_md}\n\n"
                f"### Draft Notice / Counter-Proposal (Requires HITL Approval Before Sending)\n"
                f"```text\n{draft_email}\n```"
            )
        else:
            content = f"Deterministic mock synthesis completed for task '{request.task}'."

        return LLMResponse(
            provider="mock",
            model="deterministic-procurement-v1",
            content=content,
            pii_redacted=self.settings.llm_redact_pii_for_cloud,
            redactions_count=0,
        )


def get_llm_router(request: Request) -> LLMRouter:
    """Return the configured LLM router attached to FastAPI state."""
    router: LLMRouter = request.app.state.llm_router
    return router
