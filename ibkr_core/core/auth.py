import os
from fastapi import Header, HTTPException

_API_KEY = os.getenv("IBKR_API_KEY", "")
# Default to False (fail-closed): production deployments must explicitly set
# DEV_MODE=true to bypass auth. Previously defaulted to "true", which shipped
# unauthenticated APIs if operators forgot to set it.
_DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Rejects requests missing a valid X-Api-Key header.

    Fail-closed policy:
      - DEV_MODE=true AND IBKR_API_KEY unset: bypass auth (local dev only)
      - DEV_MODE=false (default) AND IBKR_API_KEY unset: 500 error (must configure)
      - IBKR_API_KEY set: require matching X-Api-Key header
    """
    if _DEV_MODE and not _API_KEY:
        return

    if not _API_KEY:
        raise HTTPException(
            status_code=500,
            detail="IBKR_API_KEY environment variable is not set. "
                   "Set it for production, or set DEV_MODE=true for local development."
        )

    if x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
