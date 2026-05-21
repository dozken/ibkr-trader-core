import os
from fastapi import Header, HTTPException

_API_KEY = os.getenv("IBKR_API_KEY", "")
_DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Rejects requests missing a valid X-Api-Key header.
    Can be bypassed ONLY if DEV_MODE=true and IBKR_API_KEY is empty.
    """
    if _DEV_MODE and not _API_KEY:
        return

    if not _API_KEY:
        raise HTTPException(
            status_code=500,
            detail="IBKR_API_KEY environment variable is not set."
        )

    if x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
