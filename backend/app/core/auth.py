import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import HTTPException, Request
from pydantic import BaseModel

from app.core.config import Settings

_PBKDF2_ITERATIONS = 120_000

VALID_ROLES: frozenset[str] = frozenset(
    {
        "analyst",
        "procurement_manager",
        "legal_counsel",
        "finance_director",
        "vp_finance",
        "admin",
    }
)

ROLE_APPROVAL_SCOPE: dict[str, set[str]] = {
    "admin": {"admin", "vp_finance", "finance_director", "legal_counsel", "procurement_manager"},
    "vp_finance": {"vp_finance", "finance_director", "procurement_manager"},
    "finance_director": {"finance_director", "procurement_manager"},
    "legal_counsel": {"legal_counsel", "procurement_manager"},
    "procurement_manager": {"procurement_manager"},
    "analyst": set(),
}


class TokenPayload(BaseModel):
    """Decoded claims from a signed HS256 access token."""

    sub: str
    email: str
    full_name: str
    role: str
    exp: int


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with a random 16-byte salt."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(computed, expected)


def create_access_token(
    *,
    user_id: str,
    email: str,
    full_name: str,
    role: str,
    settings: Settings,
) -> str:
    """Mint a signed HS256 JWT access token."""
    header = {"alg": "HS256", "typ": "JWT"}
    exp = int(time.time()) + (settings.jwt_expire_minutes * 60)
    payload = {
        "sub": user_id,
        "email": email,
        "full_name": full_name,
        "role": role,
        "exp": exp,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(settings.auth_secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    """Verify signature and expiry on an HS256 JWT token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Malformed bearer token")

    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        if header.get("alg") != "HS256":
            raise HTTPException(status_code=401, detail="Unsupported token algorithm")

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(
            settings.auth_secret_key.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise HTTPException(status_code=401, detail="Invalid token signature")

        raw_payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        parsed = TokenPayload(**raw_payload)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc

    if parsed.exp < int(time.time()):
        raise HTTPException(status_code=401, detail="Bearer token has expired")
    return parsed


def role_can_approve(actor_role: str, required_role: str) -> bool:
    """Return True if actor_role holds authority to decide an approval for required_role."""
    allowed = ROLE_APPROVAL_SCOPE.get(actor_role.strip().lower(), set())
    return required_role.strip().lower() in allowed


def extract_bearer_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header if present."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header scheme")
    return parts[1].strip()


def get_optional_current_user(request: Request) -> TokenPayload | None:
    """Validate Bearer JWT when supplied, or require it when AUTH_REQUIRED is enabled."""
    settings: Settings = request.app.state.settings
    token = extract_bearer_token(request)
    if token is None:
        if settings.auth_required:
            raise HTTPException(status_code=401, detail="Authentication required")
        return None
    return decode_access_token(token, settings)


def require_authenticated_user(request: Request) -> TokenPayload:
    """Require a valid Bearer JWT regardless of global AUTH_REQUIRED setting."""
    settings: Settings = request.app.state.settings
    token = extract_bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_access_token(token, settings)
