from datetime import datetime, timezone


def as_utc(dt: datetime | None) -> datetime | None:
    """Make any datetime timezone-aware in UTC. Naive values are treated as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)