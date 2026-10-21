import os
from typing import Any, Optional

from fastapi import HTTPException

from server.models import DEFAULT_TENANT_ID
from server.rate_limit import check_rate_limit

DEFAULT_AI_TENANT_DAILY_LIMIT = 1000
DEFAULT_AI_USER_DAILY_LIMIT = 50
DEFAULT_AI_RATE_LIMIT_WINDOW_SECONDS = 24 * 3600


def _int_env(name: str, default: int, *, minimum: int = 0, maximum: Optional[int] = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(value, maximum)
    return value


def ai_generation_window_seconds() -> int:
    return _int_env("AI_RATE_LIMIT_WINDOW_SECONDS", DEFAULT_AI_RATE_LIMIT_WINDOW_SECONDS, minimum=60, maximum=31 * 24 * 3600)


def ai_tenant_generation_limit() -> int:
    return _int_env("AI_TENANT_DAILY_LIMIT", DEFAULT_AI_TENANT_DAILY_LIMIT, minimum=0, maximum=1_000_000)


def ai_user_generation_limit() -> int:
    return _int_env("AI_USER_DAILY_LIMIT", DEFAULT_AI_USER_DAILY_LIMIT, minimum=0, maximum=100_000)


def _quota_detail() -> str:
    return "AI 生成过于频繁，请稍后再试"


def check_ai_generation_quota(
    *,
    tenant_id: str | None,
    user_id: Any = None,
    raise_http_exception: bool = True,
) -> None:
    tenant = str(tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    window_seconds = ai_generation_window_seconds()
    tenant_limit = ai_tenant_generation_limit()
    user_limit = ai_user_generation_limit()

    try:
        if tenant_limit > 0:
            check_rate_limit(
                f"ai:tenant:{tenant}",
                tenant_limit,
                window_seconds,
                detail=_quota_detail(),
            )
        if user_limit > 0 and user_id is not None:
            user_key = str(user_id).strip()
            if user_key:
                check_rate_limit(
                    f"ai:user:{tenant}:{user_key}",
                    user_limit,
                    window_seconds,
                    detail=_quota_detail(),
                )
    except HTTPException as exc:
        if raise_http_exception:
            raise
        raise ValueError(str(exc.detail or "AI 生成过于频繁，请稍后再试")) from exc
