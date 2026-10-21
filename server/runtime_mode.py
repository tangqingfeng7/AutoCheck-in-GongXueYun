import os


BACKGROUND_ROLES = {"all", "worker", "background", "scheduler"}
API_ONLY_ROLES = {"api", "web"}


def _role() -> str:
    return (os.getenv("APP_ROLE") or os.getenv("PROCESS_ROLE") or "all").strip().lower()


def _flag(name: str) -> str:
    return (os.getenv(name) or "").strip().lower()


def should_start_background_services() -> bool:
    disabled = _flag("DISABLE_BACKGROUND_SERVICES")
    if disabled in {"1", "true", "yes", "on"}:
        return False

    enabled = _flag("ENABLE_BACKGROUND_SERVICES")
    if enabled in {"1", "true", "yes", "on"}:
        return True

    role = _role()
    if role in API_ONLY_ROLES:
        return False
    return role in BACKGROUND_ROLES or not role
