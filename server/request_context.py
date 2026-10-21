import contextvars
import re
import uuid
from contextlib import contextmanager
from typing import Iterator, Optional


_REQUEST_ID = contextvars.ContextVar("request_id", default="")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def normalize_request_id(value: Optional[str]) -> str:
    candidate = str(value or "").strip()
    if _REQUEST_ID_RE.match(candidate):
        return candidate
    return uuid.uuid4().hex


def get_request_id() -> str:
    return str(_REQUEST_ID.get() or "")


@contextmanager
def request_context(request_id: Optional[str]) -> Iterator[str]:
    normalized = normalize_request_id(request_id)
    token = _REQUEST_ID.set(normalized)
    try:
        yield normalized
    finally:
        _REQUEST_ID.reset(token)
