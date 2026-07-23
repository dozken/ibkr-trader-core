"""Gateway container control.

Manages the IB Gateway Docker containers (start/stop/restart/status) via the
Docker socket, plus a worker reconnect endpoint. Requires the backend to have
the Docker socket mounted (see docker-compose). No-ops gracefully when the
socket or containers are unavailable.
"""
import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from ibkr_core.core.auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

DOCKER_SOCK = "/var/run/docker.sock"
# Hardened deploys front the Docker socket with a whitelisted socket-proxy
# (Tecnativa) so the backend never mounts the raw root-equivalent socket. Set
# DOCKER_PROXY_URL=http://docker-socket-proxy:2375 to route the gateway
# start/stop/restart calls through it (TCP); unset = direct unix socket (dev).
DOCKER_PROXY_URL = os.getenv("DOCKER_PROXY_URL", "").strip()
GATEWAY_CONTAINERS = {
    "paper": "ibkr-gateway-paper",
    "live": "ibkr-gateway-live",
}


def _docker_client() -> httpx.Client:
    """A client bound to either the socket-proxy (TCP) or the raw unix socket."""
    if DOCKER_PROXY_URL:
        return httpx.Client(base_url=DOCKER_PROXY_URL)
    transport = httpx.HTTPTransport(uds=DOCKER_SOCK)
    return httpx.Client(transport=transport, base_url="http://docker")


def _docker_get(path: str) -> dict:
    with _docker_client() as c:
        r = c.get(path, timeout=10)
        r.raise_for_status()
        return r.json()


def _docker_post(path: str) -> int:
    with _docker_client() as c:
        r = c.post(path, timeout=30)
        return r.status_code


@router.get("/status")
def gateway_status():
    results = {}
    for key, name in GATEWAY_CONTAINERS.items():
        try:
            info = _docker_get(f"/containers/{name}/json")
            results[key] = {
                "name": name,
                "running": info["State"]["Running"],
                "status": info["State"]["Status"],
            }
        except Exception:
            results[key] = {"name": name, "running": False, "status": "unavailable"}
    return results


@router.get("/auth")
def gateway_auth(request: Request):
    """True authentication / data-health, distinct from container 'running'.

    Container 'running' (see /status) only means the Docker process is up. This
    reports whether each account's IBKR API socket is actually connected
    (= logged in past 2FA) and whether market data is being blocked by a
    competing live session (logged in elsewhere via web/mobile/TWS).
    """
    am = getattr(request.app.state, "account_manager", None)
    worker = getattr(request.app.state, "worker", None)

    accounts = []
    workers = []
    if am and am.list_account_ids():
        for aid in am.list_account_ids():
            w = am.get_worker_by_id(aid)
            if w:
                workers.append((aid, w))
    elif worker:
        workers.append(("primary", worker))

    any_connected = False
    for aid, w in workers:
        connected = False
        try:
            connected = bool(w.ib.isConnected())
        except Exception:
            connected = False
        any_connected = any_connected or connected
        accounts.append({
            "account_id": aid,
            "authenticated": connected,  # API socket up = logged in past 2FA
            "host": getattr(w, "host", None),
            "port": getattr(w, "port", None),
        })

    # Detect a recent competing-session block (IBKR error 10197) from the worker.
    competing = bool(getattr(worker, "_competing_session", False)) if worker else False

    return {
        "any_authenticated": any_connected,
        "competing_session": competing,
        "accounts": accounts,
        "note": (
            "Competing session detected — another IBKR login (web/mobile/TWS) is "
            "holding market data. Log out elsewhere, then Reconnect."
            if competing else None
        ),
    }


@router.post("/{gateway}/stop", dependencies=[Depends(require_api_key)])
def gateway_stop(gateway: str):
    if gateway not in GATEWAY_CONTAINERS:
        raise HTTPException(400, f"Unknown gateway: {gateway}. Use: {list(GATEWAY_CONTAINERS)}")
    name = GATEWAY_CONTAINERS[gateway]
    code = _docker_post(f"/containers/{name}/stop?t=10")
    if code in (204, 304):
        logger.info("Gateway %s stopped", name)
        return {"ok": True, "gateway": gateway, "action": "stopped"}
    raise HTTPException(500, f"Docker stop returned {code}")


@router.post("/{gateway}/start", dependencies=[Depends(require_api_key)])
def gateway_start(gateway: str):
    if gateway not in GATEWAY_CONTAINERS:
        raise HTTPException(400, f"Unknown gateway: {gateway}. Use: {list(GATEWAY_CONTAINERS)}")
    name = GATEWAY_CONTAINERS[gateway]
    code = _docker_post(f"/containers/{name}/start")
    if code in (204, 304):
        logger.info("Gateway %s started", name)
        return {"ok": True, "gateway": gateway, "action": "started"}
    raise HTTPException(500, f"Docker start returned {code}")


@router.post("/{gateway}/restart", dependencies=[Depends(require_api_key)])
def gateway_restart(gateway: str):
    if gateway not in GATEWAY_CONTAINERS:
        raise HTTPException(400, f"Unknown gateway: {gateway}. Use: {list(GATEWAY_CONTAINERS)}")
    name = GATEWAY_CONTAINERS[gateway]
    code = _docker_post(f"/containers/{name}/restart?t=10")
    if code == 204:
        logger.info("Gateway %s restarted — 2FA will be sent to IBKR mobile", name)
        return {"ok": True, "gateway": gateway, "action": "restarted"}
    raise HTTPException(500, f"Docker restart returned {code}")


@router.post("/reconnect", dependencies=[Depends(require_api_key)])
async def gateway_reconnect(request: Request):
    """Force all workers to disconnect and reconnect to their gateways."""
    am = getattr(request.app.state, "account_manager", None)
    worker = getattr(request.app.state, "worker", None)
    disconnected = []
    if am:
        for aid in am.list_account_ids():
            w = am.get_worker_by_id(aid)
            if w:
                w.disconnect()
                disconnected.append(aid)
    elif worker:
        worker.disconnect()
        disconnected.append("primary")
    logger.info("Gateway reconnect: disconnected workers %s — main_loop will auto-reconnect", disconnected)
    return {"ok": True, "disconnected": disconnected, "note": "Workers will auto-reconnect within ~10s"}
