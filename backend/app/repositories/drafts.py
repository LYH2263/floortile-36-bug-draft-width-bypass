"""Estimate drafts: two-phase persistence (draft -> confirm).

A draft snapshots room/tile dimensions and the computed result. Confirming a
draft is the ONLY way a calc_run row is written, and it happens in the same
transaction as the draft status flip, so a successful confirm always implies
exactly one new history row.
"""

import json
from datetime import datetime, timedelta, timezone

from app.config import DRAFT_TTL_MINUTES
from app.db import connect

STATUS_OPEN = "open"
STATUS_CONFIRMED = "confirmed"


class DraftError(Exception):
    """Domain error raised while confirming a draft.

    code: not_found | expired | already_confirmed | stale
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_draft(
    room_id: int,
    tile_id: int,
    waste_pct: float,
    room: dict,
    tile: dict,
    result: dict,
    note: str = "",
    ttl_minutes: float | None = None,
) -> dict:
    """Persist a draft snapshot. Does NOT touch calc_runs (history)."""
    now = _now()
    ttl = DRAFT_TTL_MINUTES if ttl_minutes is None else float(ttl_minutes)
    expires_at = now + timedelta(minutes=ttl)
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO estimate_drafts(
                room_id, tile_id, waste_pct,
                room_length, room_width, tile_l, tile_w,
                result_json, note, status, expires_at, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                room_id,
                tile_id,
                float(waste_pct),
                float(room["length"]),
                float(room["width"]),
                float(tile["tile_l"]),
                float(tile["tile_w"]),
                json.dumps(result, ensure_ascii=False),
                note,
                STATUS_OPEN,
                expires_at.isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()
        draft_id = int(cur.lastrowid)
    finally:
        conn.close()
    return {
        "draft_id": draft_id,
        "room_id": room_id,
        "tile_id": tile_id,
        "waste_pct": float(waste_pct),
        "status": STATUS_OPEN,
        "expires_at": expires_at.isoformat(),
        "created_at": now.isoformat(),
        "result": result,
    }


def get_draft(draft_id: int):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM estimate_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["result"] = json.loads(d.pop("result_json"))
        return d
    finally:
        conn.close()


def confirm_draft(draft_id: int) -> dict:
    """Confirm a draft: write exactly one calc_run in the SAME transaction.

    Fails (and writes nothing) when the draft is missing, expired, already
    confirmed, or the room/tile dimensions no longer match the snapshot.
    """
    conn = connect()
    try:
        # BEGIN IMMEDIATE: take the write lock up front so the status check
        # and the run insert cannot interleave with another confirm.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM estimate_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if not row:
            raise DraftError("not_found", f"draft {draft_id} not found")
        draft = dict(row)

        now = _now()
        if draft["status"] != STATUS_OPEN:
            raise DraftError(
                "already_confirmed", f"draft {draft_id} already confirmed"
            )
        if now >= _parse_ts(draft["expires_at"]):
            raise DraftError("expired", f"draft {draft_id} expired")

        room = conn.execute(
            "SELECT * FROM rooms WHERE id=?", (draft["room_id"],)
        ).fetchone()
        tile = conn.execute(
            "SELECT * FROM tiles WHERE id=?", (draft["tile_id"],)
        ).fetchone()
        if not room or not tile:
            raise DraftError("stale", "room or tile no longer exists")
        room = dict(room)
        tile = dict(tile)
        # Any drift from the snapshot — room length/width or tile dims —
        # invalidates the draft; the caller must create a fresh one.
        dims_mismatch = (
            float(room["length"]) != float(draft["room_length"])
            or float(room["width"]) != float(draft["room_width"])
            or float(tile["tile_l"]) != float(draft["tile_l"])
            or float(tile["tile_w"]) != float(draft["tile_w"])
        )
        if dims_mismatch:
            raise DraftError(
                "stale", "room/tile dimensions changed since the draft was created"
            )

        # Confirm never recomputes: the stored run is the draft's snapshot.
        payload_json = draft["result_json"]
        cur = conn.execute(
            """
            INSERT INTO calc_runs(room_id, tile_id, waste_pct, result_json, note, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                draft["room_id"],
                draft["tile_id"],
                draft["waste_pct"],
                payload_json,
                draft["note"] or "",
                now.isoformat(),
            ),
        )
        run_id = int(cur.lastrowid)

        # Guarded flip: only an 'open' draft can be confirmed, exactly once.
        upd = conn.execute(
            """
            UPDATE estimate_drafts
            SET status=?, confirmed_at=?, run_id=?
            WHERE id=? AND status=?
            """,
            (STATUS_CONFIRMED, now.isoformat(), run_id, draft_id, STATUS_OPEN),
        )
        if upd.rowcount != 1:
            raise DraftError(
                "already_confirmed", f"draft {draft_id} already confirmed"
            )

        conn.commit()
        return {
            "draft_id": draft_id,
            "run_id": run_id,
            "room_id": draft["room_id"],
            "tile_id": draft["tile_id"],
            "waste_pct": draft["waste_pct"],
            "confirmed_at": now.isoformat(),
            "result": json.loads(payload_json),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
