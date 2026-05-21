import asyncio
import logging
from typing import Any, List, Literal, Union

from fastapi import WebSocket
from pydantic import BaseModel

WS_TICKERS = "/ws/tickers"

logger = logging.getLogger(__name__)


class WSBaseMessage(BaseModel):
    type: str


class TickerUpdate(WSBaseMessage):
    type: Literal["ticker_update"] = "ticker_update"
    data: Any


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Union[WSBaseMessage, dict]):
        data = message.model_dump() if isinstance(message, WSBaseMessage) else message
        dead: list = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead.append(connection)
        for conn in dead:
            logger.debug("Removing dead WebSocket connection from broadcast pool")
            self.active_connections.remove(conn)
