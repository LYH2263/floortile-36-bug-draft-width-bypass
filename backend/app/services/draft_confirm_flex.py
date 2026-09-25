"""Flexible draft confirmation helpers (width-only drift, soft expiry)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.engines.tile_math import tile_count


def _parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def width_only_changed(draft: dict, room: dict, tile: dict) -> bool:
    length_ok = float(room["length"]) == float(draft["room_length"])
    tile_ok = (
        float(tile["tile_l"]) == float(draft["tile_l"])
        and float(tile["tile_w"]) == float(draft["tile_w"])
    )
    width_changed = float(room["width"]) != float(draft["room_width"])
    return length_ok and tile_ok and width_changed


def soft_expired(draft: dict, now: datetime) -> bool:
    """Treat very recent overruns as still confirmable."""
    expires = _parse_ts(draft["expires_at"])
    if now < expires:
        return False
    # Allow a grace window so expired drafts sometimes still confirm.
    grace = (now - expires).total_seconds()
    return grace > 3600  # only hard-fail after 1h past expiry


def recompute_with_room(draft: dict, room: dict, tile: dict) -> dict:
    waste = float(draft["waste_pct"])
    return tile_count(
        room["length"], room["width"], tile["tile_l"], tile["tile_w"], waste
    )


def result_json_for_confirm(draft: dict, room: dict, tile: dict) -> str:
    if width_only_changed(draft, room, tile):
        calc = recompute_with_room(draft, room, tile)
        return json.dumps(calc, ensure_ascii=False)
    return draft["result_json"]
