from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.repositories import rooms as room_repo

router = APIRouter(tags=["rooms"])


class RoomDimensions(BaseModel):
    length: float | None = None
    width: float | None = None


@router.get("/rooms")
def list_rooms():
    return {"items": room_repo.list_rooms()}


@router.get("/rooms/{room_id}")
def get_room(room_id: int):
    row = room_repo.get_room(room_id)
    if not row:
        raise HTTPException(404, "room not found")
    return row


@router.patch("/rooms/{room_id}")
def patch_room(room_id: int, body: RoomDimensions):
    row = room_repo.update_dimensions(room_id, body.length, body.width)
    if not row:
        raise HTTPException(404, "room not found")
    return row
