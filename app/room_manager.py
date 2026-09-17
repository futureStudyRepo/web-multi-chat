from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket


class RoomConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, list[tuple[WebSocket, str]]] = defaultdict(list)

    async def connect(self, room_id: int, websocket: WebSocket, nickname: str) -> None:
        await websocket.accept()
        self._rooms[room_id].append((websocket, nickname))

    def disconnect(self, room_id: int, websocket: WebSocket) -> str | None:
        disconnected_name = None
        remaining_connections: list[tuple[WebSocket, str]] = []

        for connection, nickname in self._rooms.get(room_id, []):
            if connection is websocket:
                disconnected_name = nickname
                continue
            remaining_connections.append((connection, nickname))

        if remaining_connections:
            self._rooms[room_id] = remaining_connections
        else:
            self._rooms.pop(room_id, None)

        return disconnected_name

    def user_list(self, room_id: int) -> list[str]:
        return [nickname for _, nickname in self._rooms.get(room_id, [])]

    def has_nickname(self, room_id: int, nickname: str) -> bool:
        normalized_nickname = nickname.strip().casefold()
        return any(
            active_nickname.strip().casefold() == normalized_nickname
            for _, active_nickname in self._rooms.get(room_id, [])
        )

    async def broadcast(self, room_id: int, payload: dict) -> None:
        stale_connections: list[WebSocket] = []

        for websocket, _ in self._rooms.get(room_id, []):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(room_id, websocket)

    async def close_room(self, room_id: int, code: int = 1000) -> None:
        connections = list(self._rooms.get(room_id, []))
        self._rooms.pop(room_id, None)

        for websocket, _ in connections:
            try:
                await websocket.close(code=code)
            except RuntimeError:
                pass
