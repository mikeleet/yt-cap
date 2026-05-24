import sys
import os
import subprocess
import json
import threading
from datetime import datetime
from app.db import get_db
from app.models import ChannelResponse

CHANNEL_CACHE_DURATION = 3600

_YT_DLP_BIN = None


def _get_yt_dlp():
    global _YT_DLP_BIN
    if _YT_DLP_BIN:
        return _YT_DLP_BIN
    for candidate in [
        os.path.join(os.path.dirname(sys.executable), "yt-dlp"),
        "yt-dlp",
        os.path.expanduser("~/.local/bin/yt-dlp"),
    ]:
        try:
            result = subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                _YT_DLP_BIN = candidate
                return candidate
        except Exception:
            continue
    return "yt-dlp"


def resolve_channel(url: str) -> dict:
    url = url.strip().strip("/")
    if not url.startswith("http"):
        if url.startswith("@"):
            url = f"https://www.youtube.com/{url}/videos"
        elif url.startswith("UC") and len(url) == 24:
            url = f"https://www.youtube.com/channel/{url}/videos"
        else:
            url = f"https://www.youtube.com/@{url}/videos"

    if "/videos" not in url:
        url = url.rstrip("/") + "/videos"

    yt_dlp = _get_yt_dlp()
    result = subprocess.run(
        [yt_dlp, "--flat-playlist", "--dump-json", "--playlist-end", "1",
         "--no-warnings", url],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(f"Could not resolve channel: {url}")

    entry = json.loads(result.stdout.strip().split("\n")[0])
    return {
        "channel_id": entry.get("channel_id") or entry.get("playlist_channel_id", ""),
        "name": entry.get("channel") or entry.get("uploader") or entry.get("playlist_channel", ""),
        "handle": entry.get("uploader_id") or entry.get("playlist_uploader_id", ""),
    }


def get_channel(channel_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM channels WHERE channel_id = ?", [channel_id]).fetchone()
    conn.close()
    if not row:
        return None

    cols = [
        "channel_id", "name", "handle", "thumbnail_url", "auto_update",
        "update_interval", "total_videos", "captions_ok", "captions_failed",
        "last_scan_at", "last_download_at", "last_sync_at", "sync_status",
        "error_message", "current_video_id", "current_video_title",
        "progress_done", "progress_total", "current_phase",
        "created_at", "updated_at",
    ]
    ch = dict(zip(cols, row))

    from app.ratelimit import cooldown_remaining
    cooldown = cooldown_remaining()
    if cooldown > 0:
        ch["sync_status"] = "error"
        ch["error_message"] = f"Rate limited, cooldown {cooldown}s"
    elif ch["sync_status"] == "error" and cooldown <= 0:
        ch["sync_status"] = "idle"
        ch["error_message"] = None

    conn2 = get_db()
    ch["total_videos"] = conn2.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ?", [channel_id]
    ).fetchone()[0]
    ch["captions_ok"] = conn2.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'downloaded'",
        [channel_id],
    ).fetchone()[0]
    ch["captions_failed"] = conn2.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'failed'",
        [channel_id],
    ).fetchone()[0]
    conn2.close()

    if ch.get("current_video_id"):
        ch["current_progress"] = {
            "current_video": ch["current_video_id"],
            "current_title": ch.get("current_video_title") or "",
            "done": ch.get("progress_done") or 0,
            "total": ch.get("progress_total") or 0,
        }
    else:
        ch["current_progress"] = None

    return ch


def list_channels() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM channels ORDER BY name").fetchall()
    conn.close()

    cols = [
        "channel_id", "name", "handle", "thumbnail_url", "auto_update",
        "update_interval", "total_videos", "captions_ok", "captions_failed",
        "last_scan_at", "last_download_at", "last_sync_at", "sync_status",
        "error_message", "current_video_id", "current_video_title",
        "progress_done", "progress_total", "current_phase",
        "created_at", "updated_at",
    ]
    channels = [dict(zip(cols, r)) for r in rows]

    from app.ratelimit import cooldown_remaining
    for ch in channels:
        cooldown = cooldown_remaining()
        if cooldown > 0:
            ch["sync_status"] = "error"
            ch["error_message"] = f"Rate limited, cooldown {cooldown}s"
        elif ch["sync_status"] == "error" and cooldown <= 0:
            ch["sync_status"] = "idle"
            ch["error_message"] = None

        # If idle and another channel is downloading → show as queued
        if ch["sync_status"] == "idle":
            conn2 = get_db()
            active = conn2.execute(
                "SELECT COUNT(*) FROM channels WHERE sync_status = 'downloading' AND channel_id != ?",
                [ch["channel_id"]],
            ).fetchone()[0]
            conn2.close()
            if active > 0:
                ch["sync_status"] = "queued"
                ch["error_message"] = "Waiting for other channel to finish"

        conn2 = get_db()
        ch["total_videos"] = conn2.execute(
            "SELECT COUNT(*) FROM videos WHERE channel_id = ?", [ch["channel_id"]]
        ).fetchone()[0]
        ch["captions_ok"] = conn2.execute(
            "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'downloaded'",
            [ch["channel_id"]],
        ).fetchone()[0]
        ch["captions_failed"] = conn2.execute(
            "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'failed'",
            [ch["channel_id"]],
        ).fetchone()[0]
        conn2.close()

        if ch.get("current_video_id"):
            ch["current_progress"] = {
                "current_video": ch["current_video_id"],
                "current_title": ch.get("current_video_title") or "",
                "done": ch.get("progress_done") or 0,
                "total": ch.get("progress_total") or 0,
                "phase": ch.get("current_phase") or "",
            }
        else:
            ch["current_progress"] = None

    return channels


def add_channel(info: dict) -> str:
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO channels (channel_id, name, handle, sync_status, update_interval, auto_update) VALUES (?, ?, ?, 'idle', 43200, true)",
        [info["channel_id"], info["name"], info.get("handle")],
    )
    conn.close()
    return info["channel_id"]


def update_channel(channel_id: str, **kwargs) -> bool:
    allowed = {"auto_update", "update_interval"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    conn = get_db()
    exists = conn.execute("SELECT 1 FROM channels WHERE channel_id = ?", [channel_id]).fetchone()
    if not exists:
        conn.close()
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [channel_id]
    conn.execute(
        f"UPDATE channels SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE channel_id = ?",
        values,
    )
    conn.close()
    return True


def delete_channel(channel_id: str) -> bool:
    conn = get_db()
    exists = conn.execute("SELECT 1 FROM channels WHERE channel_id = ?", [channel_id]).fetchone()
    if not exists:
        conn.close()
        return False
    conn.execute("DELETE FROM videos WHERE channel_id = ?", [channel_id])
    conn.execute("DELETE FROM channels WHERE channel_id = ?", [channel_id])
    conn.close()
    return True


def set_sync_status(channel_id: str, status: str, error: str | None = None):
    conn = get_db()
    conn.execute(
        "UPDATE channels SET sync_status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE channel_id = ?",
        [status, error, channel_id],
    )
    conn.close()


def update_channel_counts(channel_id: str):
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ?", [channel_id]).fetchone()[0]
    ok_count = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'downloaded'",
        [channel_id],
    ).fetchone()[0]
    failed_count = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'failed'",
        [channel_id],
    ).fetchone()[0]
    conn.execute(
        "UPDATE channels SET total_videos = ?, captions_ok = ?, captions_failed = ?, "
        "last_scan_at = CURRENT_TIMESTAMP, last_sync_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
        "WHERE channel_id = ?",
        [total, ok_count, failed_count, channel_id],
    )
    conn.close()


def set_last_download_at(channel_id: str):
    conn = get_db()
    conn.execute(
        "UPDATE channels SET last_download_at = CURRENT_TIMESTAMP WHERE channel_id = ?",
        [channel_id],
    )
    conn.close()


def get_channel_status(channel_id: str) -> dict | None:
    ch = get_channel(channel_id)
    if not ch:
        return None

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ?", [channel_id]).fetchone()[0]
    ok_count = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'downloaded'",
        [channel_id],
    ).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND caption_status = 'failed'",
        [channel_id],
    ).fetchone()[0]
    skipped = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND never_download = true",
        [channel_id],
    ).fetchone()[0]
    conn.close()

    from app.ratelimit import cooldown_remaining
    from app.scheduler import get_download_progress, get_download_history
    cooldown_secs = cooldown_remaining()
    progress = get_download_progress(channel_id)

    sync_status = ch["sync_status"] or "idle"
    error_message = ch.get("error_message")

    if cooldown_secs > 0:
        sync_status = "error"
        error_message = f"Rate limited, cooldown {cooldown_secs}s"
    elif sync_status == "error" and not cooldown_secs:
        sync_status = "idle"
        error_message = None

    # If idle and another channel is downloading → show as queued
    if sync_status == "idle":
        conn3 = get_db()
        active = conn3.execute(
            "SELECT COUNT(*) FROM channels WHERE sync_status = 'downloading' AND channel_id != ?",
            [channel_id],
        ).fetchone()[0]
        conn3.close()
        if active > 0:
            sync_status = "queued"
            error_message = "Waiting for other channel to finish"

    pending = total - ok_count - failed - skipped

    return {
        "channel_id": ch["channel_id"],
        "name": ch["name"],
        "sync_status": sync_status,
        "total_videos": total,
        "captions_ok": ok_count,
        "captions_failed": failed,
        "captions_pending": max(pending, 0),
        "captions_skipped": skipped,
        "last_scan_at": ch.get("last_scan_at"),
        "last_download_at": ch.get("last_download_at"),
        "last_sync_at": ch.get("last_sync_at"),
        "current_progress": progress,
        "error_message": error_message,
    }
