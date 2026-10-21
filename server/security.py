import ipaddress
import hmac
import os
import secrets
import socket
from urllib.parse import urlparse

from fastapi import HTTPException


SAFE_CSRF_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
AUTH_COOKIE_NAMES = {"admin_auth_token", "app_auth_token"}
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
INVALID_CSRF_ORIGIN = "invalid-csrf-origin"
AUTH_BOOTSTRAP_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/app/auth/login",
    "/api/app/auth/register",
    "/auth/login",
    "/auth/register",
    "/app/auth/login",
    "/app/auth/register",
}
DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-src 'self' https://www.openstreetmap.org; "
    "font-src 'self' data:; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

UNSAFE_APP_SECRETS = {
    "please-change-me-in-production",
    "replace-with-a-long-random-secret",
    "change-me",
    "changeme",
    "secret",
}

UNSAFE_ADMIN_PASSWORDS = {
    "admin",
    "admin123456",
    "password",
    "123456",
    "change-me",
    "changeme",
}

UNSAFE_USER_PASSWORDS = UNSAFE_ADMIN_PASSWORDS | {
    "qwerty123",
    "12345678",
    "123456789",
    "11111111",
}


def env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def env_flag_default(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def int_env(name: str, default: int, *, min_value: int = 1, max_value: int = 256) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def apply_security_headers(response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if not env_flag("DISABLE_CSP"):
        response.headers.setdefault("Content-Security-Policy", os.getenv("CONTENT_SECURITY_POLICY") or DEFAULT_CSP)
    if env_flag_default("ENABLE_HSTS", is_production()):
        response.headers.setdefault(
            "Strict-Transport-Security",
            os.getenv("HSTS_HEADER") or "max-age=15552000; includeSubDomains",
        )


def app_env() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()


def is_production() -> bool:
    return app_env() in {"prod", "production"}


def require_safe_app_secret(value: str) -> None:
    secret = (value or "").strip()
    if not (is_production() or env_flag("REQUIRE_APP_SECRET")):
        return
    if not secret:
        raise RuntimeError("APP_SECRET 未配置（生产环境必须设置）")
    lowered = secret.lower()
    if (
        lowered in UNSAFE_APP_SECRETS
        or "change" in lowered
        or "replace" in lowered
        or "example" in lowered
        or len(secret) < 32
    ):
        raise RuntimeError("APP_SECRET 不安全，请使用至少 32 位的随机密钥")


def require_safe_admin_credentials(username: str, password: str) -> None:
    if not is_production():
        return
    if not (username or "").strip() or not (password or "").strip():
        raise RuntimeError("生产环境必须设置 ADMIN_USERNAME / ADMIN_PASSWORD")
    lowered = (password or "").strip().lower()
    if (
        lowered in UNSAFE_ADMIN_PASSWORDS
        or "change" in lowered
        or "password" in lowered
        or len((password or "").strip()) < 12
    ):
        raise RuntimeError("ADMIN_PASSWORD 不安全，请使用至少 12 位的非默认密码")


def require_password_strength(password: str, *, min_length: int | None = None, label: str = "Password") -> str:
    value = (password or "").strip()
    min_len = int(min_length or int_env("USER_PASSWORD_MIN_LENGTH", 10, min_value=8, max_value=100))
    if len(value) < min_len or len(value) > 100:
        raise HTTPException(status_code=400, detail=f"{label} length must be {min_len}-100 characters")
    lowered = value.lower()
    if (
        lowered in UNSAFE_USER_PASSWORDS
        or "password" in lowered
        or "123456" in lowered
        or "change" in lowered
        or lowered == "admin"
    ):
        raise HTTPException(status_code=400, detail=f"{label} is too weak")
    return value


def _is_private_or_special_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return bool(
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        )
    except Exception:
        return True


def is_safe_outbound_url(url: str, *, allow_private: bool = False) -> bool:
    if allow_private:
        return True

    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").strip()
    if not host or host.lower() == "localhost":
        return False
    port = parsed.port or 443
    if port != 443:
        return False

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception:
        return False

    return all(not _is_private_or_special_ip(info[4][0]) for info in infos)


def _split_env_list(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace(";", ",").split(",") if item.strip()]


def _strip_wrapping(value: str) -> str:
    stripped = (value or "").strip()
    while len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"', "`"}:
        stripped = stripped[1:-1].strip()
    return stripped


def _normalize_origin(value: str) -> str:
    parsed = urlparse(_strip_wrapping(value))
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        return ""
    port = parsed.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    if port and not default_port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def _configured_frontend_origins() -> set[str]:
    origins: set[str] = set()
    for env_name in ("FRONTEND_ORIGINS", "CORS_ORIGINS"):
        for item in _split_env_list(os.getenv(env_name) or ""):
            normalized = _normalize_origin(item)
            if normalized and normalized != "*":
                origins.add(normalized)
    if not is_production():
        origins.update({"http://localhost:5173", "http://127.0.0.1:5173"})
    return origins


def _request_target_origin(request) -> str:
    url = getattr(request, "url", None)
    if url is None:
        return ""
    scheme = (getattr(url, "scheme", "") or "").lower()
    host = (getattr(url, "hostname", "") or "").lower()
    if not scheme or not host:
        return ""
    port = getattr(url, "port", None)
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    if port and not default_port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def _request_source_origin(request) -> str:
    headers = getattr(request, "headers", {}) or {}
    origin = headers.get("origin")
    if origin is not None:
        return _normalize_origin(origin) or INVALID_CSRF_ORIGIN
    referer = headers.get("referer")
    if referer is not None:
        return _normalize_origin(referer) or INVALID_CSRF_ORIGIN
    return ""


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _csrf_token_matches(cookies, headers) -> bool:
    cookie_token = str((cookies or {}).get(CSRF_COOKIE_NAME) or "")
    header_token = str((headers or {}).get(CSRF_HEADER_NAME) or (headers or {}).get("x-xsrf-token") or "")
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)


def should_reject_cookie_csrf(request) -> bool:
    if (getattr(request, "method", "") or "").upper() in SAFE_CSRF_METHODS:
        return False

    request_path = str(getattr(getattr(request, "url", None), "path", "") or "")
    if request_path in AUTH_BOOTSTRAP_PATHS:
        source_origin = _request_source_origin(request)
        if not source_origin:
            return False
        target_origin = _request_target_origin(request)
        if source_origin == target_origin:
            return False
        return source_origin not in _configured_frontend_origins()

    cookies = getattr(request, "cookies", {}) or {}
    if not any(cookies.get(name) for name in AUTH_COOKIE_NAMES):
        return False

    headers = getattr(request, "headers", {}) or {}
    authorization = (headers.get("authorization") or "").strip().lower()
    if authorization.startswith("bearer "):
        return False

    if not _csrf_token_matches(cookies, headers):
        return True

    source_origin = _request_source_origin(request)
    if not source_origin:
        return False

    target_origin = _request_target_origin(request)
    if source_origin == target_origin:
        return False

    return source_origin not in _configured_frontend_origins()


def require_metrics_access(request) -> None:
    token = (os.getenv("METRICS_AUTH_TOKEN") or "").strip()
    if not token:
        if is_production():
            raise HTTPException(status_code=403, detail="metrics access denied")
        return

    headers = getattr(request, "headers", {}) or {}
    presented = (headers.get("x-metrics-token") or "").strip()
    if not presented:
        authorization = (headers.get("authorization") or "").strip()
        if authorization.lower().startswith("bearer "):
            presented = authorization[7:].strip()
    if presented != token:
        raise HTTPException(status_code=403, detail="metrics access denied")


def is_trusted_proxy(remote_ip: str) -> bool:
    if env_flag("TRUST_PROXY_HEADERS") and not is_production():
        return True

    remote = (remote_ip or "").strip()
    if not remote:
        return False

    for item in _split_env_list(os.getenv("TRUSTED_PROXY_IPS") or ""):
        try:
            if "/" in item:
                if ipaddress.ip_address(remote) in ipaddress.ip_network(item, strict=False):
                    return True
            elif remote == item:
                return True
        except Exception:
            continue
    return False


def client_ip_from_request(request) -> str:
    remote_ip = request.client.host if getattr(request, "client", None) else "unknown"
    if is_trusted_proxy(remote_ip):
        xff = request.headers.get("x-forwarded-for") if getattr(request, "headers", None) else None
        if xff:
            return xff.split(",")[0].strip()
    return remote_ip
