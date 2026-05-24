from datetime import datetime, timedelta
from app.db import get_db


def list_videos(
    channel_id: str | None = None,
    last_n: int | None = None,
    days: int | None = None,
    status: str | None = None,
    since: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    conn = get_db()
    conditions = []
    params = []

    if channel_id:
        conditions.append("v.channel_id = ?")
        params.append(channel_id)
    if status:
        conditions.append("v.caption_status = ?")
        params.append(status)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        conditions.append("COALESCE(v.publish_date, v.first_seen_at) >= ?")
        params.append(cutoff.isoformat())
    if since:
        conditions.append("v.caption_at >= ?")
        params.append(since)

    where = " AND ".join(conditions) if conditions else "1=1"

    order = "COALESCE(v.publish_date, v.first_seen_at) DESC NULLS LAST"
    if last_n:
        order = "COALESCE(v.publish_date, v.first_seen_at) DESC NULLS LAST"
        limit = last_n

    query = f"""
        SELECT v.* FROM videos v
        WHERE {where}
        ORDER BY {order}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()

    cols = [
        "video_id", "channel_id", "title", "url", "thumbnail_url",
        "duration_sec", "publish_date", "caption_status", "caption_lang",
        "caption_text", "caption_chars", "never_download", "retry_count",
        "last_error", "first_seen_at", "caption_at", "updated_at",
    ]
    return [dict(zip(cols, r)) for r in rows]


def get_video(video_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM videos WHERE video_id = ?", [video_id]).fetchone()
    conn.close()
    if not row:
        return None
    cols = [
        "video_id", "channel_id", "title", "url", "thumbnail_url",
        "duration_sec", "publish_date", "caption_status", "caption_lang",
        "caption_text", "caption_chars", "never_download", "retry_count",
        "last_error", "first_seen_at", "caption_at", "updated_at",
    ]
    return dict(zip(cols, row))


def update_video(video_id: str, **kwargs) -> bool:
    allowed = {"never_download", "caption_status", "caption_lang", "caption_text",
               "caption_chars", "retry_count", "last_error", "caption_at", "publish_date"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    conn = get_db()
    exists = conn.execute("SELECT 1 FROM videos WHERE video_id = ?", [video_id]).fetchone()
    if not exists:
        conn.close()
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [video_id]
    conn.execute(
        f"UPDATE videos SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE video_id = ?",
        values,
    )
    conn.close()
    return True


def get_caption(video_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT video_id, title, caption_lang, caption_text, caption_chars FROM videos WHERE video_id = ? AND caption_status = 'downloaded'",
        [video_id],
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "video_id": row[0],
        "title": row[1],
        "language": row[2],
        "text": row[3] or "",
        "chars": row[4] or 0,
    }


def delete_caption(video_id: str) -> bool:
    conn = get_db()
    exists = conn.execute("SELECT 1 FROM videos WHERE video_id = ? AND caption_text IS NOT NULL", [video_id]).fetchone()
    if not exists:
        conn.close()
        return False
    conn.execute(
        "UPDATE videos SET caption_text = NULL, caption_chars = NULL, caption_lang = NULL, caption_status = 'none', caption_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE video_id = ?",
        [video_id],
    )
    conn.close()
    return True


def upsert_video(video: dict) -> bool:
    conn = get_db()
    existing = conn.execute(
        "SELECT video_id, caption_status, caption_text FROM videos WHERE video_id = ?",
        [video["video_id"]],
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE videos SET
                title = ?, url = ?, thumbnail_url = ?, duration_sec = ?,
                publish_date = ?, updated_at = CURRENT_TIMESTAMP
            WHERE video_id = ?
            """,
            [
                video["title"], video["url"], video.get("thumbnail_url"),
                video.get("duration_sec"), video.get("publish_date"),
                video["video_id"],
            ],
        )
        conn.close()
        return False
    else:
        conn.execute(
            """
            INSERT INTO videos (video_id, channel_id, title, url, thumbnail_url, duration_sec, publish_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                video["video_id"], video["channel_id"], video["title"],
                video["url"], video.get("thumbnail_url"),
                video.get("duration_sec"), video.get("publish_date"),
            ],
        )
        conn.close()
        return True
