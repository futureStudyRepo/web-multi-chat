from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .db import ChatRepository
from .room_manager import RoomConnectionManager

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Web Multi Chat Demo")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

repository = ChatRepository(BASE_DIR / "data" / "rooms.db")
manager = RoomConnectionManager()


class RoomCreateRequest(BaseModel):
    name: str
    password: str | None = None


class RoomJoinRequest(BaseModel):
    nickname: str
    password: str | None = None


class RoomDeleteRequest(BaseModel):
    password: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
        },
    )


@app.get("/api/rooms")
async def list_rooms():
    return {"rooms": repository.list_rooms()}


@app.post("/api/rooms", status_code=201)
async def create_room(payload: RoomCreateRequest):
    try:
        room = repository.create_room(payload.name, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"room": room}


@app.get("/api/rooms/{room_id}")
async def get_room(room_id: int):
    room = repository.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")

    return {
        "room": room,
        "users": manager.user_list(room_id),
    }


@app.post("/api/rooms/{room_id}/join")
async def join_room(room_id: int, payload: RoomJoinRequest):
    room = repository.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")

    nickname = payload.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="Nickname is required.")

    if not repository.verify_room_password(room_id, payload.password):
        raise HTTPException(status_code=403, detail="Room password is invalid.")

    if manager.has_nickname(room_id, nickname):
        raise HTTPException(status_code=409, detail="Nickname is already in use in this room.")

    return {
        "room": room,
        "messages": repository.list_messages(room_id),
        "users": manager.user_list(room_id),
    }


@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: int, payload: RoomDeleteRequest):
    room = repository.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")

    if not repository.verify_room_password(room_id, payload.password):
        raise HTTPException(status_code=403, detail="Room password is invalid.")

    deleted = repository.delete_room(room_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Room not found.")

    await manager.close_room(room_id, code=4001)
    return {"ok": True}


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: int):
    initial_room = repository.get_room(room_id)
    if initial_room is None:
        await websocket.close(code=4404)
        return

    nickname = websocket.query_params.get("nickname", "").strip() or "guest"
    password = websocket.query_params.get("password", "")

    if not repository.verify_room_password(room_id, password):
        await websocket.close(code=4403)
        return

    if manager.has_nickname(room_id, nickname):
        await websocket.close(code=4409)
        return

    await manager.connect(room_id, websocket, nickname)

    join_event = repository.save_message(
        room_id=room_id,
        event_type="system",
        nickname=nickname,
        message=f"{nickname} joined the room.",
    )
    room = repository.get_room(room_id) or initial_room
    await manager.broadcast(
        room_id,
        {
            **join_event,
            "users": manager.user_list(room_id),
            "room": room,
        },
    )

    try:
        while True:
            text = await websocket.receive_text()
            message = repository.save_message(
                room_id=room_id,
                event_type="chat",
                nickname=nickname,
                message=text,
            )
            room = repository.get_room(room_id) or room
            await manager.broadcast(
                room_id,
                {
                    **message,
                    "users": manager.user_list(room_id),
                    "room": room,
                },
            )
    except WebSocketDisconnect:
        disconnected_name = manager.disconnect(room_id, websocket)
        if disconnected_name:
            leave_event = repository.save_message(
                room_id=room_id,
                event_type="system",
                nickname=disconnected_name,
                message=f"{disconnected_name} left the room.",
            )
            room = repository.get_room(room_id) or room
            await manager.broadcast(
                room_id,
                {
                    **leave_event,
                    "users": manager.user_list(room_id),
                    "room": room,
                },
            )
