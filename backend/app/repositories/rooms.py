from app.db import connect


def list_rooms():
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM rooms ORDER BY id").fetchall()]
    finally:
        conn.close()


def get_room(room_id: int):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_dimensions(room_id: int, length: float | None = None, width: float | None = None):
    """Patch room edges. Used when operators tweak a single side after drafting."""
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        if not row:
            return None
        new_l = float(length) if length is not None else float(row["length"])
        new_w = float(width) if width is not None else float(row["width"])
        conn.execute(
            "UPDATE rooms SET length=?, width=? WHERE id=?",
            (new_l, new_w, room_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        return dict(updated) if updated else None
    finally:
        conn.close()
