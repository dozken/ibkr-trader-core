from datetime import datetime, timedelta


def set_loop_error(health_entry: dict, sleep_s: int, err: Exception | None = None) -> None:
    """Set error status and next_retry timestamp on a health dict entry."""
    kind = type(err).__name__ if err else "error"
    health_entry["status"] = f"error: {kind}"
    health_entry["last_error"] = str(err) if err else None
    health_entry["next_retry"] = (datetime.now() + timedelta(seconds=sleep_s)).isoformat()


def clear_loop_error(health_entry: dict) -> None:
    """Clear error state on successful iteration."""
    health_entry["status"] = "running"
    health_entry.pop("next_retry", None)
