"""Single source of truth for reading the wall clock.

Every "now" in this codebase means UTC. That was already true in production by
accident rather than intent: the containers set TZ=Etc/UTC, so a naive
`datetime.now()` happened to equal UTC. It is not true on a developer's laptop,
and it stops being true the moment TZ changes — which for a bot trading US, EU
and Asian sessions off day counts and cooldowns is a silent correctness bug, not
a style question. Spelling it once here keeps the guarantee.

Values written before this migration are naive UTC, so anything read back from
disk or the DB must go through `as_utc()` before being compared against an
aware now() — otherwise Python raises TypeError on aware-vs-naive comparison.
"""
from datetime import date, datetime, timezone


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def utc_today() -> date:
    """Current UTC calendar date. `date.today()` would read local time."""
    return datetime.now(timezone.utc).date()


def db_now() -> datetime:
    """Naive UTC "now", matching the DB's TIMESTAMP WITHOUT TIME ZONE columns.

    Values used in a query against those columns must stay naive. Passing an
    aware datetime leans on an implicit server-side cast that only happens to
    agree while the session TZ is UTC, and the same mix raises TypeError
    outright in plain Python comparisons. Same instant as `utc_now()`, tzinfo
    dropped at the storage boundary and nowhere else.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(dt: datetime) -> datetime:
    """Return `dt` as an aware UTC datetime, assuming naive values are UTC.

    Naive values are what every pre-migration timestamp on disk and in the
    DB looks like (the columns are TIMESTAMP WITHOUT TIME ZONE). Treat them as
    the UTC they always were rather than crashing or silently shifting them.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
