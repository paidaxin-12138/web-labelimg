from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.services.redis_service import LockService, PubSubService, get_redis

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.project_connections: dict[str, dict[str, WebSocket]] = {}
        self.image_connections: dict[str, dict[str, WebSocket]] = {}

    async def connect_project(self, project_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.project_connections.setdefault(project_id, {})[user_id] = websocket

    def disconnect_project(self, project_id: str, user_id: str) -> None:
        self.project_connections.get(project_id, {}).pop(user_id, None)

    async def connect_image(self, image_id: str, user_id: str, websocket: WebSocket) -> None:
        self.image_connections.setdefault(image_id, {})[user_id] = websocket

    def disconnect_image(self, image_id: str, user_id: str) -> None:
        self.image_connections.get(image_id, {}).pop(user_id, None)

    async def broadcast_image(self, image_id: str, message: dict, exclude: Optional[str] = None) -> None:
        for uid, ws in self.image_connections.get(image_id, {}).items():
            if uid != exclude:
                await ws.send_json(message)

    async def broadcast_project(self, project_id: str, message: dict) -> None:
        for ws in self.project_connections.get(project_id, {}).values():
            await ws.send_json(message)


manager = ConnectionManager()


def envelope(msg_type: str, payload: dict, sender: dict) -> dict:
    return {
        "type": msg_type,
        "payload": payload,
        "sender": sender,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id": str(uuid.uuid4()),
    }


@router.websocket("/ws/projects/{project_id}")
async def project_ws(websocket: WebSocket, project_id: str, token: str):
    try:
        payload = decode_token(token, expected_type="access")
        user_id = payload["sub"]
    except ValueError:
        await websocket.close(code=4401)
        return

    redis = await get_redis()
    lock_service = LockService(redis)
    pubsub = PubSubService(redis)

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.models import User

        user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = user_result.scalar_one_or_none()
        if not user:
            await websocket.close(code=4401)
            return
        sender = {"user_id": user_id, "display_name": user.display_name}

    await manager.connect_project(project_id, user_id, websocket)
    await manager.broadcast_project(
        project_id,
        envelope("presence", {"online_users": list(manager.project_connections[project_id].keys())}, sender),
    )

    current_image_id: Optional[str] = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")
            payload = data.get("payload", {})

            if msg_type == "ping":
                await websocket.send_json(envelope("pong", {}, sender))
                continue

            if msg_type == "join_image":
                current_image_id = payload.get("image_id")
                if current_image_id:
                    await manager.connect_image(current_image_id, user_id, websocket)
                    ok, lock = await lock_service.acquire(current_image_id, user_id, sender["display_name"])
                    await websocket.send_json(
                        envelope("lock_status", {"image_id": current_image_id, "is_editor": ok, "lock": lock}, sender)
                    )
                continue

            if msg_type == "leave_image" and current_image_id:
                await lock_service.release(current_image_id, user_id)
                manager.disconnect_image(current_image_id, user_id)
                current_image_id = None
                continue

            if msg_type == "cursor_move" and current_image_id:
                msg = envelope("cursor_move", {"image_id": current_image_id, **payload}, sender)
                await manager.broadcast_image(current_image_id, msg, exclude=user_id)
                continue

            if msg_type in {"annotation_add", "annotation_update", "annotation_delete", "annotation_move"}:
                image_id = payload.get("image_id") or current_image_id
                if not image_id:
                    continue
                lock = await lock_service.get(image_id)
                if not lock or lock.get("user_id") != user_id:
                    await websocket.send_json(envelope("conflict", {"message": "Read-only"}, sender))
                    continue
                await lock_service.renew(image_id, user_id)
                msg = envelope(msg_type, payload, sender)
                await manager.broadcast_image(image_id, msg, exclude=user_id)
                continue

    except WebSocketDisconnect:
        if current_image_id:
            await lock_service.release(current_image_id, user_id)
            manager.disconnect_image(current_image_id, user_id)
        manager.disconnect_project(project_id, user_id)
