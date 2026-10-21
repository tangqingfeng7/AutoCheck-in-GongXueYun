import base64
import hashlib
import logging
import os
from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc$"
logger = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _secret_encryption_required() -> bool:
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    return _env_flag("REQUIRE_SECRET_ENCRYPTION") or app_env in {"prod", "production"}


def _get_fernet() -> Fernet | None:
    key = (os.getenv("USER_PASSWORD_KEY") or os.getenv("FERNET_KEY") or "").strip()
    if not key:
        return None
    try:
        raw = key.encode("utf-8")
        if len(raw) == 44:
            return Fernet(raw)
    except Exception as exc:
        logger.debug("invalid Fernet key format, deriving key from passphrase: %s", exc)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def encrypt_secret(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    f = _get_fernet()
    if not f:
        if _secret_encryption_required():
            raise ValueError("生产环境必须配置 USER_PASSWORD_KEY 或 FERNET_KEY 后才能保存敏感信息")
        return s
    token = f.encrypt(s.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"

def decrypt_secret(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if not s.startswith(_PREFIX):
        return s
    f = _get_fernet()
    if not f:
        raise ValueError("密钥未配置，无法解密")
    token = s[len(_PREFIX) :]
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("密钥错误或密文损坏")
