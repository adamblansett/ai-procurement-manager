import hashlib
import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

_SYNONYM_GROUPS: dict[str, tuple[str, ...]] = {
    "liability": ("cap", "damages", "limitation", "indemnity"),
    "cap": ("liability", "ceiling", "limit", "maximum"),
    "uplift": ("escalator", "increase", "cpi", "renewal"),
    "escalator": ("uplift", "increase", "cpi"),
    "renewal": ("auto-renew", "notice", "expiration", "window"),
    "termination": ("convenience", "cancel", "exit", "refund"),
    "convenience": ("termination", "exit", "notice"),
    "breach": ("dpa", "security", "gdpr", "residency", "hours"),
    "dpa": ("gdpr", "soc2", "residency", "breach"),
    "sla": ("uptime", "availability", "credits"),
    "payment": ("net", "invoice", "terms"),
}


def generate_embedding(text: str, dimensions: int = 384) -> list[float]:
    """Generate a deterministic normalized semantic embedding vector for clause text."""
    vec = [0.0] * dimensions
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return vec

    weighted_terms: list[tuple[str, float]] = []
    for tok in tokens:
        weighted_terms.append((tok, 1.0))
        for syn in _SYNONYM_GROUPS.get(tok, ()):
            weighted_terms.append((syn, 0.45))

    for idx in range(len(tokens) - 1):
        weighted_terms.append((f"{tokens[idx]}_{tokens[idx + 1]}", 1.25))

    for term, weight in weighted_terms:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        raw_int = int.from_bytes(digest, "big")
        bucket = raw_int % dimensions
        sign = 1.0 if ((raw_int >> 16) & 1) == 0 else -1.0
        vec[bucket] += sign * weight

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0.0:
        return vec
    return [round(v / norm, 6) for v in vec]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return round(dot / (norm_a * norm_b), 4)
