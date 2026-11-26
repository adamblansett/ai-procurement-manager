from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    VALID_ROLES,
    TokenPayload,
    create_access_token,
    get_optional_current_user,
    hash_password,
    require_authenticated_user,
    verify_password,
)
from app.core.config import Settings
from app.core.database import get_app_settings, get_db
from app.core.governance import record_audit_event
from app.core.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=180)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = "analyst"


class UserLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=180)
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    """Register a user account (restricted to admin tokens in production)."""
    if settings.app_env.strip().lower() == "production":
        current_user = get_optional_current_user(request)
        if current_user is None or current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Self-registration is disabled in production; admin token required.",
            )

    normalized_role = payload.role.strip().lower()
    if normalized_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{payload.role}'")

    normalized_email = payload.email.strip().lower()
    existing = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    user = User(
        email=normalized_email,
        full_name=payload.full_name.strip(),
        role=normalized_role,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await record_audit_event(
        db,
        actor=user.full_name,
        action="user.registered",
        entity_type="user",
        entity_id=user.id,
        summary=f"Registered user {user.email} with role '{user.role}'.",
    )
    await db.commit()
    await db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        settings=settings,
    )
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login_user(
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    """Authenticate by email and password and return a signed HS256 Bearer token."""
    normalized_email = payload.email.strip().lower()
    user = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        settings=settings,
    )
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def get_current_user_profile(
    current: TokenPayload = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the currently authenticated user profile."""
    user = await db.get(User, current.sub)
    if user is None:
        raise HTTPException(status_code=404, detail="Authenticated user record not found")
    return user


@router.get("/users", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    """List active RBAC users (safe profile fields only)."""
    rows = (
        (await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.role.asc())))
        .scalars()
        .all()
    )
    return list(rows)
