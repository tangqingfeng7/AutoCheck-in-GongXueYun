import logging

logger = logging.getLogger(__name__)


def safe_external_error_detail(message: str, exc: Exception | None = None) -> str:
    detail = str(message or "External request failed").strip() or "External request failed"
    if exc is not None:
        logger.debug("%s failed with %s", detail, exc.__class__.__name__)
    return detail
