import datetime


UTC = datetime.timezone.utc


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(UTC)
