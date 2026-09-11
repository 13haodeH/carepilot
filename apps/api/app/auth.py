"""Supabase JWT verification and server-enforced CarePilot roles."""

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError
from sqlalchemy.orm import Session

from .database import get_db
from .models import Profile


ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"
VALID_ROLES = frozenset({ROLE_USER, ROLE_ADMIN, ROLE_SUPERADMIN})


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    display_name: str
    role: str


def _supabase_url() -> str:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    if not url:
        raise HTTPException(status_code=503, detail="登录服务尚未配置，请联系管理员")
    return url


@lru_cache(maxsize=1)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


def _verified_claims(token: str) -> dict:
    supabase_url = _supabase_url()
    jwks_url = (os.getenv("SUPABASE_JWKS_URL") or f"{supabase_url}/auth/v1/.well-known/jwks.json").strip()
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "EdDSA"],
            audience="authenticated",
            issuer=f"{supabase_url}/auth/v1",
        )
    except (InvalidTokenError, PyJWKClientError, ValueError, OSError) as error:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录") from error


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    claims = _verified_claims(authorization.removeprefix("Bearer ").strip())
    user_id = str(claims.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    profile = db.get(Profile, user_id)
    if not profile or profile.role not in VALID_ROLES:
        raise HTTPException(status_code=403, detail="账号权限尚未准备好，请稍后重试")
    return CurrentUser(
        id=user_id,
        email=str(claims.get("email") or ""),
        display_name=profile.display_name,
        role=profile.role,
    )


def require_roles(*roles: str):
    allowed = frozenset(roles)

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="你没有访问此页面的权限")
        return user

    return dependency
