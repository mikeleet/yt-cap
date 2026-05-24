import subprocess
import json
import asyncio
import time as _time
import traceback
from datetime import datetime
from app.db import get_db
from app.channel import set_sync_status, update_channel_counts, set_last_download_at, _get_yt_dlp
from app.video import upsert_video, update_video, get_video
from app.captions import fetch_caption, RateLimitError
from app.rate_limiter import rate_limiter
from app.ratelimit import can_proceed, set_cooldown as set_global_cooldown, cooldown_remaining
from app.sse import sse_manager

COOLDOWN_BASE = 180  # 3 minutes when rate-limited
_download_progress: dict[str, dict] = {}
_download_history: dict[str, list[dict]] = {}


def _set_progress(channel_id: str, **kwargs):
    conn = get_db()
    updates = []
    params = []
    if "current_video" in kwargs:
        updates.append("current_video_id = ?")
        params.append(kwargs["current_video"])
    if "current_title" in kwargs:
        updates.append("current_video_title = ?")
        params.append(kwargs["current_title"][:200])
    if "done" in kwargs:
        updates.append("progress_done = ?")
        params.append(kwargs["done"])
    if "total" in kwargs:
        updates.append("progress_total = ?")
        params.append(kwargs["total"])
    if "phase" in kwargs:
        updates.append("current_phase = ?")
        params.append(kwargs["phase"])
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(channel_id)
        conn.execute(
            f"UPDATE channels SET {', '.join(updates)} WHERE channel_id = ?",
            params,
        )
    conn.close()


def _add_history(channel_id: str, event: str, video_id: str, details: str = ""):
    h = _download_history.setdefault(channel_id, [])
    h.insert(0, {
        "time": datetime.utcnow().isoformat(),
        "event": event,
        "video_id": video_id,
        "details": details,
    })
    if len(h) > 50:
        h.pop()


def get_download_progress(channel_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT current_video_id, current_video_title, progress_done, progress_total, current_phase FROM channels WHERE channel_id = ?",
        [channel_id],
    ).fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    return {
        "current_video": row[0],
        "current_title": row[1] or "",
        "done": row[2] or 0,
        "total": row[3] or 0,
        "phase": row[4] or "",
    }


def get_download_history(channel_id: str) -> list[dict]:
    return _download_history.get(channel_id, [])[:20]


def _enrich_video_date(video_id: str) -> str | None:
    try:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            upload_date = info.get("upload_date")
            if upload_date and len(upload_date) == 8:
                return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    except Exception:
        pass
    return None



def scan_channel_videos(channel_id: str, incremental: bool = False) -> list[dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT handle FROM channels WHERE channel_id = ?", [channel_id]
    ).fetchone()
    conn.close()

    if not row:
        return []

    handle = row[0] or channel_id
    if handle.startswith("@"):
        url = f"https://www.youtube.com/{handle}/videos"
    elif handle.startswith("UC") and len(handle) == 24:
        url = f"https://www.youtube.com/channel/{handle}/videos"
    else:
        url = f"https://www.youtube.com/channel/{channel_id}/videos"

    yt_dlp = _get_yt_dlp()
    base_cmd = [
        yt_dlp,
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        url,
    ]

    # Chunked: fetch playlists in batches to handle channels with 1000s of videos
    # Full scan: 200 per chunk. Incremental: 50 per chunk.
    # YouTube rate limit: 10s delay between chunks.
    chunk_size = 50 if incremental else 200
    scan_label = "Incremental scan" if incremental else "Full scan"
    offset_chunk = 0
    all_videos = []
    chunk_total = None  # estimated total chunks, set after first response

    while True:
        if offset_chunk > 0:
            # Respect global cooldown before each chunk
            while not can_proceed():
                _time.sleep(5)
            # Small delay between chunks to avoid rate limits
            _time.sleep(3)

        cmd = list(base_cmd)  # fresh command each iteration
        start = 1 + offset_chunk * chunk_size
        end = start + chunk_size - 1
        cmd.insert(2, "--playlist-end")
        cmd.insert(3, str(end))
        if offset_chunk > 0:
            cmd.insert(2, "--playlist-start")
            cmd.insert(3, str(start))

        # Send chunk progress via SSE
        if chunk_total:
            from app.sse import sse_manager
            sse_manager.send(channel_id, "scanning", {
                "message": f"{scan_label} – chunk {offset_chunk + 1}/{chunk_total} ({chunk_size} videos each)",
                "scan_type": "full" if not incremental else "incremental",
                "chunk_current": offset_chunk + 1,
                "chunk_total": chunk_total,
            })

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0 or not result.stdout.strip():
            if offset_chunk == 0:
                raise RuntimeError(f"yt-dlp failed: {result.stderr[:200]}")
            break  # subsequent chunk failure = end of playlist

        batch = []
        playlist_count = None
        for line in result.stdout.strip().split("\n"):
            try:
                entry = json.loads(line)
                if playlist_count is None:
                    playlist_count = entry.get("playlist_count")
                thumb = None
                if entry.get("thumbnails"):
                    thumb = entry["thumbnails"][-1].get("url")
                pub_date = None
                ts = entry.get("timestamp")
                if ts:
                    pub_date = datetime.utcfromtimestamp(ts).isoformat()
                batch.append({
                    "video_id": entry["id"],
                    "channel_id": channel_id,
                    "title": entry.get("title", ""),
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}",
                    "thumbnail_url": thumb,
                    "duration_sec": int(entry["duration"]) if entry.get("duration") else None,
                    "publish_date": pub_date,
                })
            except (json.JSONDecodeError, KeyError):
                continue

        # Set total chunks from playlist_count on first batch
        if chunk_total is None and playlist_count:
            import math
            chunk_total = math.ceil(playlist_count / chunk_size)

        # Send chunk progress SSE
        if chunk_total:
            from app.sse import sse_manager
            sse_manager.send(channel_id, "scanning", {
                "message": f"{scan_label} – chunk {offset_chunk + 1}/{chunk_total} ({chunk_size} videos each)",
                "scan_type": "full" if not incremental else "incremental",
                "chunk_current": offset_chunk + 1,
                "chunk_total": chunk_total,
            })

        all_videos.extend(batch)
        offset_chunk += 1

        # Stop when batch is smaller than chunk_size (last page)
        if len(batch) < chunk_size:
            break

    return all_videos


def process_channel_scan(channel_id: str, incremental: bool = False) -> dict:
    conn = get_db()
    current_status = conn.execute(
        "SELECT sync_status FROM channels WHERE channel_id = ?", [channel_id]
    ).fetchone()
    conn.close()
    prev_status = current_status[0] if current_status else "idle"

    try:
        # If a download is in progress, scan silently without changing status
        if prev_status != "downloading":
            sse_manager.send(channel_id, "scanning", {"message": "Discovering videos..."})
            set_sync_status(channel_id, "scanning")

        total = 0
        new_count = 0
        new_ids = []

        videos = scan_channel_videos(channel_id, incremental=incremental)
        total = len(videos)
        for v in videos:
            is_new = upsert_video(v)
            if is_new:
                new_count += 1
                new_ids.append(v["video_id"])

        update_channel_counts(channel_id)

        # Metadata (publish_date, duration) comes free from caption downloads.
        # No separate enrichment needed — removed to avoid extra API calls.

        if prev_status != "downloading":
            set_sync_status(channel_id, "idle")
    except Exception:
        # Always reset status on failure so we don't get stuck
        if prev_status != "downloading":
            set_sync_status(channel_id, "idle")
        raise

    sse_manager.send(channel_id, "scan_complete", {
        "total": total,
        "new": new_count,
        "message": f"Found {total} videos ({new_count} new)",
    })
    return {"total": total, "new": new_count}


def process_channel_download(channel_id: str):
    try:
        cooldown = cooldown_remaining()
        if cooldown > 0:
            sse_manager.send(channel_id, "cooldown", {
                "message": f"Cannot download — cooldown {cooldown}s remaining",
                "cooldown_seconds": cooldown,
            })
            sse_manager.send(channel_id, "download_complete", {
                "downloaded": 0, "failed": 0, "cooldown": True,
            })
            return

        # Only one channel downloads at a time — let the older process run
        conn = get_db()
        active = conn.execute(
            "SELECT COUNT(*) FROM channels WHERE sync_status = 'downloading' AND channel_id != ?",
            [channel_id],
        ).fetchone()[0]
        conn.close()
        if active > 0:
            sse_manager.send(channel_id, "queued", {
                "message": "Another download in progress — queued for next cycle",
            })
            return

        set_sync_status(channel_id, "downloading")

        conn = get_db()
        rows = conn.execute(
            "SELECT video_id FROM videos WHERE channel_id = ? AND caption_status IN ('none', 'failed') "
            "AND never_download = false",
            [channel_id],
        ).fetchall()
        conn.close()

        pending = len(rows)
        to_download = [r[0] for r in rows]

        downloaded = 0
        failed = 0
        consecutive_rate_limits = 0

        _set_progress(channel_id, total=pending, done=0, failed=0, current_video=None, phase="starting")
        for vid in to_download:
            current_video = get_video(vid)

            _set_progress(channel_id, current_video=vid,
                         current_title=current_video["title"][:60] if current_video else vid,
                         done=downloaded, failed=failed, total=pending, phase="browser_launch")

            try:
                rate_limiter.acquire()
                result, error = fetch_caption(vid)

                if result:
                    update_fields = dict(
                        caption_status="downloaded",
                        caption_lang=result.language,
                        caption_text=result.text,
                        caption_chars=len(result.text),
                        caption_at=datetime.utcnow().isoformat(),
                        last_error=None,
                        retry_count=0,
                    )
                    update_video(vid, **update_fields)
                    # Free metadata from the download page
                    if result.publish_date:
                        update_video(vid, publish_date=result.publish_date)
                    if result.duration_sec:
                        update_video(vid, duration_sec=result.duration_sec)
                    downloaded += 1
                    _add_history(channel_id, "downloaded", vid, f"{len(result.text)} chars, {result.language}")
                elif error.startswith("no_transcript"):
                    reason = error.split(":", 1)[1] if ":" in error else "no transcript"
                    update_video(vid, caption_status="unavailable", last_error=reason[:500])
                    failed += 1
                    _add_history(channel_id, "unavailable", vid, reason)
                else:
                    retry = (current_video["retry_count"] if current_video else 0) + 1
                    if retry >= 5:
                        update_video(vid, caption_status="unavailable", last_error=error, retry_count=retry)
                        _add_history(channel_id, "unavailable", vid, f"gave up after {retry} tries: {error}")
                    else:
                        update_video(vid, caption_status="failed", last_error=error, retry_count=retry)
                        _add_history(channel_id, "failed", vid, f"retry {retry}/5: {error}")
                    failed += 1

            except RateLimitError as e:
                retry = (current_video["retry_count"] if current_video else 0) + 1
                if retry >= 5:
                    update_video(vid, caption_status="unavailable", last_error="rate_limited", retry_count=retry)
                    _add_history(channel_id, "unavailable", vid, f"gave up after {retry} rate limits")
                else:
                    update_video(vid, caption_status="failed", last_error="rate_limited", retry_count=retry)
                failed += 1
                cooldown = e.cooldown if e.cooldown > 0 else COOLDOWN_BASE
                set_global_cooldown(cooldown)
                _add_history(channel_id, "rate_limited", vid, f"cooldown {cooldown}s")
                break

            except Exception as e:
                retry = (current_video["retry_count"] if current_video else 0) + 1
                if retry >= 5:
                    update_video(vid, caption_status="unavailable", last_error=str(e)[:500], retry_count=retry)
                else:
                    update_video(vid, caption_status="failed", last_error=str(e)[:500], retry_count=retry)
                failed += 1

        update_channel_counts(channel_id)
        set_last_download_at(channel_id)
        set_sync_status(channel_id, "idle")

    except Exception as e:
        traceback.print_exc()
        set_sync_status(channel_id, "idle")


def process_channel_sync(channel_id: str):
    process_channel_scan(channel_id)
    process_channel_download(channel_id)


def _run_in_thread(target, *args):
    import threading
    t = threading.Thread(target=target, args=args, daemon=True)
    t.start()
    return t


def process_channel_scan_async(channel_id: str):
    return _run_in_thread(process_channel_scan, channel_id)


def process_channel_download_async(channel_id: str):
    return _run_in_thread(process_channel_download, channel_id)


def process_channel_sync_async(channel_id: str):
    return _run_in_thread(process_channel_sync, channel_id)
