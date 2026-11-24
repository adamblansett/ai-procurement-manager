import re
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.models import Contract, ContractClauseFinding, PlaybookRule
from app.contracts.schemas import (
    ClausePairDiffItem,
    ContractDetailRead,
    ContractPairComparisonRead,
    ContractRead,
)
from app.core.governance import create_approval_request, record_audit_event
from app.core.llm import LLMRequest, LLMRouter
from app.core.models import ApprovalRequest, Vendor

DEFAULT_PLAYBOOK_SPECS: tuple[dict[str, object], ...] = (
    {
        "name": "Auto-Renewal Notice Window",
        "clause_type": "auto_renewal",
        "preferred_position": "Opt-in renewal or <= 30 days non-renewal notice prior to term end.",
        "fallback_position": "45 days notice with mandatory 60-day vendor written reminder.",
        "max_acceptable_value": 30.0,
        "severity": "high",
        "guidance": (
            "Flag notice windows exceeding 30 days or silent automatic multi-year lock-ins."
        ),
    },
    {
        "name": "Annual Price Uplift Cap",
        "clause_type": "price_uplift",
        "preferred_position": "Fixed multi-year pricing (0%) or capped at <= 5.0% upon renewal.",
        "fallback_position": "Lesser of CPI or 5% maximum annual uplift.",
        "max_acceptable_value": 5.0,
        "severity": "critical",
        "guidance": "Reject uncapped CPI, prevailing list-price resets, or uplifts > 5%.",
    },
    {
        "name": "Limitation of Liability Cap",
        "clause_type": "liability_cap",
        "preferred_position": "Mutual aggregate liability cap >= 12 months fees paid/payable.",
        "fallback_position": (
            "12 months fees with 24-month super-cap for data breach and IP indemnity."
        ),
        "max_acceptable_value": 12.0,
        "severity": "critical",
        "guidance": "Require at least 12 months of fees; escalate any 3- or 6-month cap.",
    },
    {
        "name": "Standard Payment Terms",
        "clause_type": "payment_terms",
        "preferred_position": "Net 45 (minimum Net 30) from receipt of undisputed invoice.",
        "fallback_position": "Net 30 with standard 30-day invoice dispute window.",
        "max_acceptable_value": 30.0,
        "severity": "medium",
        "guidance": "Flag Net 15, upon-receipt, or full upfront prepayment clauses.",
    },
    {
        "name": "Termination for Convenience",
        "clause_type": "termination_convenience",
        "preferred_position": (
            "Customer may terminate for convenience on 30 days notice with pro-rata refund."
        ),
        "fallback_position": (
            "60 days notice for annual SOWs or termination right on material SLA failure."
        ),
        "max_acceptable_value": 60.0,
        "severity": "medium",
        "guidance": "Identify strict non-cancelable lock-ins with zero exit flexibility.",
    },
    {
        "name": "Data Residency & Breach Notice",
        "clause_type": "data_residency",
        "preferred_position": (
            "Executed DPA, SOC 2 Type II / GDPR controls, and <= 48-hour breach notice."
        ),
        "fallback_position": (
            "<= 48 hours security incident notice and US/EU regional hosting guarantee."
        ),
        "max_acceptable_value": 48.0,
        "severity": "high",
        "guidance": "Flag breach notification > 48 hours or missing DPA/security commitments.",
    },
    {
        "name": "Mutual Indemnification",
        "clause_type": "indemnification",
        "preferred_position": (
            "Mutual indemnification including uncapped vendor third-party IP indemnity."
        ),
        "fallback_position": (
            "Mutual indemnity for bodily injury, gross negligence, and IP infringement."
        ),
        "max_acceptable_value": None,
        "severity": "high",
        "guidance": "Escalate one-sided customer-only indemnification or excluded IP indemnity.",
    },
    {
        "name": "Service Level Uptime & Credits",
        "clause_type": "sla_uptime",
        "preferred_position": (
            ">= 99.9% monthly uptime commitment backed by tiered service credits."
        ),
        "fallback_position": (
            "99.9% availability with termination right after 3 consecutive SLA breaches."
        ),
        "max_acceptable_value": 99.9,
        "severity": "medium",
        "guidance": "Flag SLA targets below 99.9% or best-efforts availability without credits.",
    },
)

SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 1.35,
    "high": 1.15,
    "medium": 0.9,
    "low": 0.65,
}


@dataclass(frozen=True)
class EvaluatedClause:
    clause_type: str
    status: str
    severity: str
    vendor_excerpt: str
    playbook_position: str
    redline_suggestion: str
    deviation_score: int


def _split_segments(raw_text: str) -> list[str]:
    chunks = re.split(r"(?:\r?\n)+|(?<=[.;])\s+", raw_text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _find_excerpt(segments: list[str], keywords: tuple[str, ...]) -> str:
    matched: list[str] = []
    for seg in segments:
        lowered = seg.lower()
        if any(kw in lowered for kw in keywords):
            matched.append(seg)
        if len(matched) >= 2:
            break
    return " ".join(matched)[:600]


def _evaluate_auto_renewal(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments,
        (
            "auto-renew",
            "auto renew",
            "automatic renewal",
            "automatically renew",
            "non-renewal",
            "renewal term",
        ),
    )
    max_days = int(rule.max_acceptable_value if rule.max_acceptable_value is not None else 30.0)
    if not excerpt:
        return EvaluatedClause(
            clause_type="auto_renewal",
            status="missing",
            severity="medium",
            vendor_excerpt="No explicit auto-renewal or notice clause detected.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Insert explicit renewal clause requiring <= {max_days} days non-renewal notice "
                "or mutual written renewal."
            ),
            deviation_score=30,
        )

    lowered = excerpt.lower()
    if any(
        p in lowered
        for p in (
            "no automatic renewal",
            "opt-in",
            "shall not automatically renew",
            "mutual written agreement",
        )
    ):
        return EvaluatedClause(
            clause_type="auto_renewal",
            status="favorable",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="No redline needed; opt-in renewal protects against silent lock-in.",
            deviation_score=0,
        )

    days_match = re.search(r"(\d+)\s*(?:calendar\s+|business\s+)?days?", lowered)
    notice_days = int(days_match.group(1)) if days_match else None
    is_auto = any(
        p in lowered
        for p in ("auto-renew", "auto renew", "automatic renewal", "automatically renew")
    )

    if is_auto and (notice_days is None or notice_days > max_days):
        found_str = f"{notice_days} days" if notice_days is not None else "unspecified notice"
        score = 85 if (notice_days or 90) >= 90 else 65
        return EvaluatedClause(
            clause_type="auto_renewal",
            status="deviation",
            severity=rule.severity,
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Reduce non-renewal notice window from {found_str} to <= {max_days} days "
                "and require 60-day advance written vendor reminder."
            ),
            deviation_score=score,
        )

    return EvaluatedClause(
        clause_type="auto_renewal",
        status="compliant",
        severity="low",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion="Clause meets playbook notice window threshold.",
        deviation_score=5,
    )


def _evaluate_price_uplift(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments,
        (
            "uplift",
            "escalat",
            "price increase",
            "fee increase",
            "fees shall increase",
            "pricing increase",
            "annual increase",
            "increase by",
            "cpi",
            "price protection",
            "rate lock",
        ),
    )
    max_pct = float(rule.max_acceptable_value if rule.max_acceptable_value is not None else 5.0)
    if not excerpt:
        return EvaluatedClause(
            clause_type="price_uplift",
            status="missing",
            severity=rule.severity,
            vendor_excerpt="No renewal pricing cap or uplift protection clause detected.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Add explicit renewal price cap of <= {max_pct:.1f}% per annual term."
            ),
            deviation_score=45,
        )

    lowered = excerpt.lower()
    if any(
        p in lowered
        for p in (
            "uncapped",
            "sole discretion",
            "prevailing list",
            "without cap",
            "unlimited increase",
        )
    ):
        return EvaluatedClause(
            clause_type="price_uplift",
            status="deviation",
            severity="critical",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Replace uncapped renewal uplift language with a hard <= {max_pct:.1f}% "
                "annual cap."
            ),
            deviation_score=90,
        )

    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", lowered)
    pct = float(pct_match.group(1)) if pct_match else None
    if pct is not None and pct > max_pct:
        return EvaluatedClause(
            clause_type="price_uplift",
            status="deviation",
            severity=rule.severity,
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Cap annual price uplift from {pct:.1f}% down to <= {max_pct:.1f}%."
            ),
            deviation_score=78,
        )

    if (pct is not None and pct == 0.0) or any(
        p in lowered for p in ("price protection", "rate lock", "flat", "no increase")
    ):
        return EvaluatedClause(
            clause_type="price_uplift",
            status="favorable",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="Favorable pricing lock; preserve during renewal.",
            deviation_score=0,
        )

    return EvaluatedClause(
        clause_type="price_uplift",
        status="compliant",
        severity="low",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion="Uplift cap aligns with commercial playbook limit.",
        deviation_score=5,
    )


def _evaluate_liability_cap(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments,
        ("liability", "limitation of liability", "aggregate liability", "damages"),
    )
    min_months = float(rule.max_acceptable_value if rule.max_acceptable_value is not None else 12.0)
    if not excerpt:
        return EvaluatedClause(
            clause_type="liability_cap",
            status="missing",
            severity=rule.severity,
            vendor_excerpt="No limitation of liability clause found.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Insert mutual aggregate liability cap equal to at least "
                f"{int(min_months)} months of fees."
            ),
            deviation_score=65,
        )

    lowered = excerpt.lower()
    months_match = re.search(r"(\d+)\s*months?", lowered)
    years_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:x\s*annual|years?)", lowered)
    months: float | None = None
    if months_match:
        months = float(months_match.group(1))
    elif years_match:
        months = float(years_match.group(1)) * 12.0

    if months is not None and months < min_months:
        score = 88 if months <= 3 else 70
        return EvaluatedClause(
            clause_type="liability_cap",
            status="deviation",
            severity="critical",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Increase aggregate liability cap from {int(months)} months to at least "
                f"{int(min_months)} months of fees (with 24-month data/IP super-cap)."
            ),
            deviation_score=score,
        )

    if any(p in lowered for p in ("super-cap", "supercap", "24 months", "2x annual")):
        return EvaluatedClause(
            clause_type="liability_cap",
            status="favorable",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="Enhanced liability protection exceeds playbook baseline.",
            deviation_score=0,
        )

    if months is not None and months >= min_months:
        return EvaluatedClause(
            clause_type="liability_cap",
            status="compliant",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="Liability cap satisfies 12-month minimum threshold.",
            deviation_score=5,
        )

    return EvaluatedClause(
        clause_type="liability_cap",
        status="deviation",
        severity="high",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion=(
            f"Clarify aggregate liability cap as >= {int(min_months)} months of fees paid/payable."
        ),
        deviation_score=55,
    )


def _evaluate_payment_terms(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments,
        ("net ", "net-", "payment", "invoice", "due upon receipt", "upfront", "payable within"),
    )
    min_days = int(rule.max_acceptable_value if rule.max_acceptable_value is not None else 30.0)
    if not excerpt:
        return EvaluatedClause(
            clause_type="payment_terms",
            status="missing",
            severity="medium",
            vendor_excerpt="No explicit payment term window detected.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Specify Net {min_days} or Net 45 payment terms from receipt of "
                "undisputed invoice."
            ),
            deviation_score=30,
        )

    lowered = excerpt.lower()
    net_match = re.search(r"(?:net[-\s]*|within\s+)(\d+)\s*(?:days)?", lowered)
    days: int | None = int(net_match.group(1)) if net_match else None
    if days is None and any(
        p in lowered for p in ("upon receipt", "upfront", "in advance", "immediate")
    ):
        days = 0

    if days is not None and days < min_days:
        return EvaluatedClause(
            clause_type="payment_terms",
            status="deviation",
            severity=rule.severity,
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Extend payment terms from {days} days to Net 45 (minimum Net {min_days})."
            ),
            deviation_score=55,
        )
    if days is not None and days >= 45:
        return EvaluatedClause(
            clause_type="payment_terms",
            status="favorable",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="Favorable Net 45+ payment terms.",
            deviation_score=0,
        )

    return EvaluatedClause(
        clause_type="payment_terms",
        status="compliant",
        severity="low",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion="Payment terms meet minimum Net 30 standard.",
        deviation_score=5,
    )


def _evaluate_termination(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments,
        (
            "termination for convenience",
            "terminate for convenience",
            "non-cancelable",
            "non-cancellable",
            "terminate",
        ),
    )
    if not excerpt:
        return EvaluatedClause(
            clause_type="termination_convenience",
            status="missing",
            severity="medium",
            vendor_excerpt="No termination-for-convenience flexibility language found.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                "Add 30-day termination for convenience right with pro-rata refund of "
                "prepaid fees."
            ),
            deviation_score=35,
        )

    lowered = excerpt.lower()
    if any(
        p in lowered
        for p in (
            "no termination for convenience",
            "may not terminate for convenience",
            "non-cancelable",
            "non-cancellable",
        )
    ):
        return EvaluatedClause(
            clause_type="termination_convenience",
            status="deviation",
            severity=rule.severity,
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                "Request 30- or 60-day termination for convenience with pro-rata refund "
                "of unused fees."
            ),
            deviation_score=65,
        )
    if "convenience" in lowered:
        days_match = re.search(r"(\d+)\s*days?", lowered)
        days = int(days_match.group(1)) if days_match else 30
        status = "favorable" if days <= 30 else "compliant"
        return EvaluatedClause(
            clause_type="termination_convenience",
            status=status,
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="Termination for convenience right aligns with playbook.",
            deviation_score=0,
        )

    return EvaluatedClause(
        clause_type="termination_convenience",
        status="compliant",
        severity="low",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion=(
            "Standard termination provisions present; verify pro-rata refund language."
        ),
        deviation_score=15,
    )


def _evaluate_data_residency(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments,
        (
            "dpa",
            "data processing",
            "gdpr",
            "soc 2",
            "soc2",
            "residency",
            "breach",
            "security incident",
        ),
    )
    max_hours = int(rule.max_acceptable_value if rule.max_acceptable_value is not None else 48.0)
    if not excerpt:
        return EvaluatedClause(
            clause_type="data_residency",
            status="missing",
            severity=rule.severity,
            vendor_excerpt="No DPA, data residency, or security breach notification terms found.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Attach executed DPA requiring SOC 2 Type II compliance and <= "
                f"{max_hours}-hour breach notice."
            ),
            deviation_score=50,
        )

    lowered = excerpt.lower()
    hours_match = re.search(r"(\d+)\s*hours?", lowered)
    hours = int(hours_match.group(1)) if hours_match else None
    if any(p in lowered for p in ("no dpa", "without dpa", "disclaims security")) or (
        hours is not None and hours > max_hours
    ):
        found = f"{hours} hours" if hours is not None else "missing DPA safeguards"
        return EvaluatedClause(
            clause_type="data_residency",
            status="deviation",
            severity=rule.severity,
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Tighten security incident notification from {found} to <= {max_hours} "
                "hours and incorporate standard DPA."
            ),
            deviation_score=72,
        )

    if hours is not None and hours <= 24:
        return EvaluatedClause(
            clause_type="data_residency",
            status="favorable",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                "24-hour breach notification and DPA controls exceed playbook baseline."
            ),
            deviation_score=0,
        )

    return EvaluatedClause(
        clause_type="data_residency",
        status="compliant",
        severity="low",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion="Data protection and residency terms meet baseline.",
        deviation_score=5,
    )


def _evaluate_indemnification(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments,
        ("indemnif", "hold harmless", "ip infringement", "intellectual property claims"),
    )
    if not excerpt:
        return EvaluatedClause(
            clause_type="indemnification",
            status="missing",
            severity=rule.severity,
            vendor_excerpt="No indemnification clause found.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                "Include mutual indemnification and vendor uncapped third-party IP "
                "infringement defense."
            ),
            deviation_score=55,
        )

    lowered = excerpt.lower()
    if "mutual" in lowered:
        return EvaluatedClause(
            clause_type="indemnification",
            status="compliant",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="Mutual indemnification satisfies playbook policy.",
            deviation_score=0,
        )

    if any(
        p in lowered
        for p in ("customer shall indemnify", "only customer", "no vendor indemnification", "as-is")
    ):
        return EvaluatedClause(
            clause_type="indemnification",
            status="deviation",
            severity=rule.severity,
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                "Convert one-sided customer indemnity into mutual indemnification with "
                "vendor IP coverage."
            ),
            deviation_score=75,
        )

    return EvaluatedClause(
        clause_type="indemnification",
        status="compliant",
        severity="low",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion=(
            "Indemnification clause detected; confirm third-party IP coverage is uncapped."
        ),
        deviation_score=10,
    )


def _evaluate_sla(segments: list[str], rule: PlaybookRule) -> EvaluatedClause:
    excerpt = _find_excerpt(
        segments, ("sla", "uptime", "availability", "service level", "service credit")
    )
    min_uptime = float(rule.max_acceptable_value if rule.max_acceptable_value is not None else 99.9)
    if not excerpt:
        return EvaluatedClause(
            clause_type="sla_uptime",
            status="missing",
            severity="medium",
            vendor_excerpt="No uptime SLA or service credit schedule detected.",
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Attach SLA guaranteeing >= {min_uptime:.1f}% monthly uptime with "
                "service credits."
            ),
            deviation_score=30,
        )

    lowered = excerpt.lower()
    pct_match = re.search(r"(9\d(?:\.\d+)?)\s*%", lowered)
    uptime = float(pct_match.group(1)) if pct_match else None
    if any(p in lowered for p in ("no service credits", "best efforts", "no sla")) or (
        uptime is not None and uptime < min_uptime
    ):
        return EvaluatedClause(
            clause_type="sla_uptime",
            status="deviation",
            severity=rule.severity,
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion=(
                f"Raise uptime commitment to >= {min_uptime:.1f}% backed by tiered "
                "service credits."
            ),
            deviation_score=60,
        )
    if uptime is not None and uptime >= 99.95:
        return EvaluatedClause(
            clause_type="sla_uptime",
            status="favorable",
            severity="low",
            vendor_excerpt=excerpt,
            playbook_position=rule.preferred_position,
            redline_suggestion="99.95%+ SLA exceeds commercial baseline.",
            deviation_score=0,
        )

    return EvaluatedClause(
        clause_type="sla_uptime",
        status="compliant",
        severity="low",
        vendor_excerpt=excerpt,
        playbook_position=rule.preferred_position,
        redline_suggestion="SLA meets minimum availability standard.",
        deviation_score=5,
    )


_EVALUATORS = {
    "auto_renewal": _evaluate_auto_renewal,
    "price_uplift": _evaluate_price_uplift,
    "liability_cap": _evaluate_liability_cap,
    "payment_terms": _evaluate_payment_terms,
    "termination_convenience": _evaluate_termination,
    "data_residency": _evaluate_data_residency,
    "indemnification": _evaluate_indemnification,
    "sla_uptime": _evaluate_sla,
}


def _fallback_rule(spec: dict[str, object]) -> PlaybookRule:
    max_val_raw = spec.get("max_acceptable_value")
    max_val = float(max_val_raw) if isinstance(max_val_raw, int | float) else None
    return PlaybookRule(
        name=str(spec["name"]),
        clause_type=str(spec["clause_type"]),
        preferred_position=str(spec["preferred_position"]),
        fallback_position=str(spec.get("fallback_position", "")),
        max_acceptable_value=max_val,
        severity=str(spec.get("severity", "medium")),
        guidance=str(spec.get("guidance", "")),
        is_active=True,
    )


def _risk_level_from_score(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


async def compare_contract_against_playbook(
    db: AsyncSession,
    contract: Contract,
    llm_router: LLMRouter,
    *,
    actor: str = "procurement-engine",
) -> ContractDetailRead:
    """Evaluate a contract against active playbook rules and summarize via LLM."""
    vendor = await db.get(Vendor, contract.vendor_id)
    vendor_name = vendor.name if vendor else "Unknown Vendor"

    rules_rows = (
        (await db.execute(select(PlaybookRule).where(PlaybookRule.is_active.is_(True))))
        .scalars()
        .all()
    )
    rules_by_type: dict[str, PlaybookRule] = {rule.clause_type: rule for rule in rules_rows}
    for spec in DEFAULT_PLAYBOOK_SPECS:
        ctype = str(spec["clause_type"])
        if ctype not in rules_by_type:
            rules_by_type[ctype] = _fallback_rule(spec)

    segments = _split_segments(contract.raw_text)
    evaluations: list[EvaluatedClause] = []
    for clause_type, evaluator in _EVALUATORS.items():
        rule = rules_by_type[clause_type]
        evaluations.append(evaluator(segments, rule))

    await db.execute(
        delete(ContractClauseFinding).where(ContractClauseFinding.contract_id == contract.id)
    )

    findings: list[ContractClauseFinding] = []
    weighted_sum = 0.0
    max_weight = 0.0
    for ev in evaluations:
        weight = SEVERITY_WEIGHTS.get(ev.severity, 1.0)
        weighted_sum += ev.deviation_score * weight
        max_weight += 100.0 * weight
        row = ContractClauseFinding(
            contract_id=contract.id,
            clause_type=ev.clause_type,
            status=ev.status,
            severity=ev.severity,
            vendor_excerpt=ev.vendor_excerpt,
            playbook_position=ev.playbook_position,
            redline_suggestion=ev.redline_suggestion,
            deviation_score=ev.deviation_score,
        )
        db.add(row)
        findings.append(row)

    # Scale risk score so critical multi-clause deviations surface decisively in 0-100 range.
    raw_pct = (weighted_sum / max_weight) * 100.0 if max_weight > 0 else 0.0
    deviations = [ev.clause_type for ev in evaluations if ev.status == "deviation"]
    missing = [ev.clause_type for ev in evaluations if ev.status == "missing"]
    favorable = [ev.clause_type for ev in evaluations if ev.status == "favorable"]
    risk_score = min(100, round(raw_pct * 1.45 + len(deviations) * 4))
    risk_level = _risk_level_from_score(risk_score)

    llm_resp = await llm_router.generate(
        LLMRequest(
            task="contract_compare",
            system_prompt=(
                "You are an enterprise procurement legal analyst summarizing playbook deviations."
            ),
            user_prompt=(
                f"Summarize commercial & legal risk for contract '{contract.title}' with "
                f"vendor '{vendor_name}'. Deviations: {deviations}. Missing: {missing}."
            ),
            context={
                "vendor_name": vendor_name,
                "contract_title": contract.title,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "deviations": deviations,
                "missing_clauses": missing,
                "favorable_clauses": favorable,
            },
        )
    )

    has_severe_deviation = any(
        ev.status == "deviation" and ev.severity in {"critical", "high"} for ev in evaluations
    )
    if contract.status != "approved":
        contract.status = "redline_required" if has_severe_deviation else "in_review"
    contract.risk_score = risk_score
    contract.risk_level = risk_level
    contract.comparison_summary = llm_resp.content
    contract.llm_provider_used = llm_resp.provider
    contract.pii_redacted = llm_resp.pii_redacted
    contract.last_compared_at = datetime.now(UTC)

    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        action="contract.compared",
        entity_type="contract",
        entity_id=contract.id,
        summary=(
            f"Compared '{contract.title}' ({vendor_name}) against playbook: "
            f"risk {risk_score}/100 ({risk_level}), {len(deviations)} deviations."
        ),
        metadata={
            "risk_score": risk_score,
            "risk_level": risk_level,
            "deviations": deviations,
            "llm_provider": llm_resp.provider,
        },
    )

    base = ContractRead.model_validate(contract).model_copy(update={"vendor_name": vendor_name})
    return ContractDetailRead(**base.model_dump(), findings=findings)  # type: ignore[arg-type]


async def get_contract_detail(db: AsyncSession, contract_id: str) -> ContractDetailRead:
    contract = await db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    vendor = await db.get(Vendor, contract.vendor_id)
    vendor_name = vendor.name if vendor else ""
    findings = (
        (
            await db.execute(
                select(ContractClauseFinding)
                .where(ContractClauseFinding.contract_id == contract_id)
                .order_by(ContractClauseFinding.deviation_score.desc())
            )
        )
        .scalars()
        .all()
    )
    base = ContractRead.model_validate(contract).model_copy(update={"vendor_name": vendor_name})
    return ContractDetailRead(**base.model_dump(), findings=findings)  # type: ignore[arg-type]


async def compare_contract_pair(
    db: AsyncSession, left_id: str, right_id: str
) -> ContractPairComparisonRead:
    left_detail = await get_contract_detail(db, left_id)
    right_detail = await get_contract_detail(db, right_id)

    left_map = {f.clause_type: f for f in left_detail.findings}
    right_map = {f.clause_type: f for f in right_detail.findings}
    clause_types = sorted(set(left_map.keys()) | set(right_map.keys()) | set(_EVALUATORS.keys()))

    diffs: list[ClausePairDiffItem] = []
    left_dev_count = 0
    right_dev_count = 0
    for ctype in clause_types:
        lf = left_map.get(ctype)
        rf = right_map.get(ctype)
        l_status = lf.status if lf else "missing"
        r_status = rf.status if rf else "missing"
        if l_status == "deviation":
            left_dev_count += 1
        if r_status == "deviation":
            right_dev_count += 1

        l_score = lf.deviation_score if lf else 40
        r_score = rf.deviation_score if rf else 40
        if l_score < r_score:
            delta = f"'{left_detail.title}' is stronger ({l_status} vs {r_status})."
        elif r_score < l_score:
            delta = f"'{right_detail.title}' is stronger ({r_status} vs {l_status})."
        else:
            delta = f"Parity across both contracts ({l_status})."

        diffs.append(
            ClausePairDiffItem(
                clause_type=ctype,
                left_status=l_status,
                left_severity=lf.severity if lf else "medium",
                left_excerpt=lf.vendor_excerpt if lf else "Not present",
                right_status=r_status,
                right_severity=rf.severity if rf else "medium",
                right_excerpt=rf.vendor_excerpt if rf else "Not present",
                delta_summary=delta,
            )
        )

    if left_detail.risk_score <= right_detail.risk_score:
        recommendation = (
            f"'{left_detail.title}' carries lower commercial risk "
            f"({left_detail.risk_score}/100, {left_dev_count} deviations) vs "
            f"'{right_detail.title}' ({right_detail.risk_score}/100, "
            f"{right_dev_count} deviations)."
        )
    else:
        recommendation = (
            f"'{right_detail.title}' carries lower commercial risk "
            f"({right_detail.risk_score}/100, {right_dev_count} deviations) vs "
            f"'{left_detail.title}' ({left_detail.risk_score}/100, "
            f"{left_dev_count} deviations)."
        )

    return ContractPairComparisonRead(
        left_contract=ContractRead.model_validate(left_detail),
        right_contract=ContractRead.model_validate(right_detail),
        clause_diffs=diffs,
        recommendation=recommendation,
    )


async def request_contract_approval(
    db: AsyncSession,
    contract_id: str,
    *,
    requested_by: str,
    notes: str,
) -> ApprovalRequest:
    contract = await db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    vendor = await db.get(Vendor, contract.vendor_id)
    vendor_name = vendor.name if vendor else "Vendor"

    required_role = (
        "legal_counsel" if contract.risk_level in {"high", "critical"} else "procurement_manager"
    )
    summary = (
        f"Review {contract.contract_type} '{contract.title}' with {vendor_name} "
        f"(risk score {contract.risk_score}/100, {contract.risk_level}). "
        f"{notes}".strip()
    )
    approval = await create_approval_request(
        db,
        entity_type="contract_review",
        entity_id=contract.id,
        action_type="approve_contract_terms",
        title=f"Contract Sign-Off: {vendor_name} — {contract.title}",
        summary=summary,
        required_role=required_role,
        requested_by=requested_by,
        amount_impact=contract.annual_value,
        payload={"risk_score": contract.risk_score, "risk_level": contract.risk_level},
    )
    return approval
