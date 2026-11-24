import re
from dataclasses import dataclass

_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "tax_id",
        re.compile(r"\b(?:EIN|Tax\s*ID)\s*[:#]?\s*\d{2}-\d{7}\b", re.IGNORECASE),
        "[REDACTED_TAX_ID]",
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    (
        "account",
        re.compile(
            r"\b(?:Account|Routing)\s*(?:#|No\.?|Number)?\s*[:#-]?\s*"
            r"(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{6,34}\b"
            r"|\bIBAN\s*[:#]?\s*[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b",
            re.IGNORECASE,
        ),
        "[REDACTED_ACCOUNT]",
    ),
    (
        "card",
        re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{13,19}\b"),
        "[REDACTED_CARD]",
    ),
    (
        "phone",
        re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\w)"),
        "[REDACTED_PHONE]",
    ),
    (
        "ip_address",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        "[REDACTED_IP]",
    ),
)


@dataclass(frozen=True)
class RedactionResult:
    """Result of deterministic PII scrubbing prior to external LLM calls."""

    redacted_text: str
    redactions_count: int
    categories: list[str]


def redact_pii(text: str) -> RedactionResult:
    """Scrub common PII and financial account identifiers from outbound text."""
    if not text:
        return RedactionResult(redacted_text=text, redactions_count=0, categories=[])

    scrubbed = text
    total_count = 0
    found_categories: list[str] = []

    for category, pattern, replacement in _PATTERNS:
        scrubbed, count = pattern.subn(replacement, scrubbed)
        if count > 0:
            total_count += count
            found_categories.append(category)

    return RedactionResult(
        redacted_text=scrubbed,
        redactions_count=total_count,
        categories=sorted(found_categories),
    )
