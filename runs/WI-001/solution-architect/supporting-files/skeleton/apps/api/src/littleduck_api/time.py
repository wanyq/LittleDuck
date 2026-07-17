from datetime import UTC, datetime


def utc_now_iso() -> str:
    return utc_iso(datetime.now(UTC))


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetime cannot cross the API boundary")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
