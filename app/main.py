import os
import threading
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request, Cookie
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db, get_setting, set_setting, get_db
from app.models import (
    ChannelAddRequest,
    ChannelUpdateRequest,
    ChannelResponse,
    ChannelStatusResponse,
    VideoResponse,
    VideoUpdateRequest,
    CaptionResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)
from app.channel import (
    resolve_channel,
    add_channel,
    get_channel,
    list_channels,
    update_channel,
    delete_channel,
    get_channel_status,
)
from app.video import (
    list_videos,
    get_video,
    update_video,
    get_caption,
    delete_caption,
)
from app.scheduler import process_channel_sync_async, process_channel_scan_async, process_channel_download_async, get_download_history
from app.sse import sse_stream

API_KEY = os.getenv("YTCAP_API_KEY", "12345")
UI_PIN = os.getenv("YTCAP_UI_PIN", "5580")


def is_localhost(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "localhost", "::1")


def verify_ui_pin(request: Request, ui_session: str = Cookie(None), default=None):
    if is_localhost(request):
        return True
    pin = request.cookies.get("ui_session", "")
    return pin == UI_PIN


def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Reset any stale statuses from previous crash
    try:
        conn = get_db()
        conn.execute("UPDATE channels SET sync_status = 'idle' WHERE sync_status IN ('scanning', 'downloading')")
        conn.close()
    except Exception:
        pass
    _start_auto_resume()
    yield


def _start_auto_resume():
    def loop():
        stuck_tracker = {}
        first_pass = True
        while True:
            if not first_pass:
                time.sleep(30)
            first_pass = False
            try:
                from app.db import get_db
                from app.scheduler import process_channel_download, process_channel_scan
                from app.ratelimit import can_proceed, cooldown_remaining
                from app.channel import set_sync_status as reset_status
                from datetime import datetime, timezone

                conn = get_db()
                channels = conn.execute(
                    "SELECT channel_id, sync_status, progress_done, last_scan_at, update_interval "
                    "FROM channels WHERE auto_update = true"
                ).fetchall()
                conn.close()

                now = datetime.now(timezone.utc)
                for row in channels:
                    ch_id, status, p_done, last_scan, interval = (
                        row[0], row[1], row[2], row[3], row[4]
                    )
                    interval = interval or 43200  # default 12 hours

                    # Stuck detection for downloading / scanning
                    if status == "downloading":
                        key = f"dl:{ch_id}:{p_done}"
                        prev = stuck_tracker.get(ch_id, "")
                        if key == prev:
                            stuck_tracker[ch_id] = key
                            reset_status(ch_id, "idle")
                            status = "idle"
                    elif status == "scanning":
                        key = f"scan:{ch_id}"
                        prev = stuck_tracker.get(ch_id, "")
                        if key == prev:
                            stuck_tracker[ch_id] = key
                            reset_status(ch_id, "idle")
                            status = "idle"

                    if status == "downloading":
                        continue

                    stuck_tracker.pop(ch_id, None)

                    # Periodic scan — full on first run, incremental after
                    need_scan = False
                    is_first_scan = False
                    if last_scan is None:
                        need_scan = True
                        is_first_scan = True
                    else:
                        try:
                            if isinstance(last_scan, str):
                                last_scan_dt = datetime.fromisoformat(
                                    last_scan.replace("Z", "+00:00")
                                ).replace(tzinfo=timezone.utc)
                            else:
                                last_scan_dt = last_scan
                            elapsed = (now - last_scan_dt).total_seconds()
                            need_scan = elapsed >= interval
                        except Exception:
                            need_scan = True

                    if need_scan:
                        try:
                            process_channel_scan(ch_id, incremental=not is_first_scan)
                        except Exception:
                            pass  # scan failed — try again next loop

                    if can_proceed():
                        conn2 = get_db()
                        active = conn2.execute(
                            "SELECT COUNT(*) FROM channels WHERE sync_status = 'downloading' AND channel_id != ?",
                            [ch_id],
                        ).fetchone()[0]
                        pending = conn2.execute(
                            "SELECT COUNT(*) FROM videos WHERE channel_id = ? "
                            "AND ((caption_status IN ('none','failed') AND never_download = false) "
                            "OR (caption_status = 'unavailable' AND retry_count < 5 AND never_download = false AND last_error NOT LIKE 'no_transcript%'))",
                            [ch_id],
                        ).fetchone()[0]
                        conn2.close()
                        if pending and active == 0:
                            process_channel_download(ch_id)
            except Exception:
                pass

    t = threading.Thread(target=loop, daemon=True)
    t.start()


app = FastAPI(title="yt-cap", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    from app.db import get_db
    conn = get_db()
    channel_count = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    video_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    downloaded = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE caption_status = 'downloaded'"
    ).fetchone()[0]
    conn.close()
    return {
        "status": "ok",
        "channels": channel_count,
        "videos": video_count,
        "captions_downloaded": downloaded,
    }


@app.get("/ui")
@app.get("/")
def serve_ui(request: Request):
    if not verify_ui_pin(request):
        return HTMLResponse(_LOGIN_PAGE, status_code=401)
    ui_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(ui_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.post("/ui/login")
def ui_login(request: Request, pin: str = Query(...)):
    if pin == UI_PIN:
        resp = JSONResponse({"status": "ok"})
        resp.set_cookie("ui_session", pin, max_age=86400 * 30, httponly=True, samesite="lax")
        return resp
    raise HTTPException(status_code=401, detail="Invalid PIN")


@app.get("/vue.js")
def serve_vue(request: Request):
    if not verify_ui_pin(request):
        raise HTTPException(status_code=401, detail="PIN required")
    vue_path = os.path.join(os.path.dirname(__file__), "vue.global.prod.js")
    return FileResponse(vue_path, media_type="application/javascript")


_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>yt-cap - Login</title>
<style>
:root{--bg:#0d1117;--bg2:#161b22;--border:#30363d;--text:#c9d1d9;--accent:#58a6ff;--red:#f85149}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:32px;max-width:360px;width:90%}
.card h1{font-size:20px;margin-bottom:8px}
.card p{color:#8b949e;font-size:13px;margin-bottom:16px}
input{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:10px 14px;border-radius:8px;font-size:18px;text-align:center;letter-spacing:4px;margin-bottom:12px}
input:focus{outline:none;border-color:var(--accent)}
button{width:100%;background:var(--accent);color:#fff;border:none;padding:10px;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer}
button:hover{opacity:0.85}
.error{color:var(--red);font-size:12px;margin-top:8px;text-align:center}
</style>
</head>
<body>
<div class="card">
<h1>yt-cap</h1>
<p>Enter PIN to access the dashboard</p>
<input type="password" id="pin" placeholder="••••" maxlength="10" autofocus>
<button onclick="login()">Unlock</button>
<div id="error" class="error"></div>
</div>
<script>
async function login(){
const pin=document.getElementById('pin').value;
try{const r=await fetch('/ui/login?pin='+pin,{method:'POST'});
if(r.ok){window.location.reload()}else{document.getElementById('error').textContent='Invalid PIN'}}
catch(e){document.getElementById('error').textContent='Connection error'}}
document.getElementById('pin').addEventListener('keydown',e=>{if(e.key==='Enter')login()})
</script>
</body>
</html>"""


@app.get("/api/settings", dependencies=[Depends(verify_api_key)])
def get_settings():
    return SettingsResponse(
        max_concurrent_fetches=get_setting("max_concurrent_fetches") or "2",
        min_interval_seconds=get_setting("min_interval_seconds") or "3",
        max_per_hour=get_setting("max_per_hour") or "100",
        max_per_day=get_setting("max_per_day") or "500",
    )


@app.patch("/api/settings", dependencies=[Depends(verify_api_key)])
def update_settings(body: SettingsUpdateRequest):
    updates = {}
    for field in ["max_concurrent_fetches", "min_interval_seconds", "max_per_hour", "max_per_day"]:
        val = getattr(body, field)
        if val is not None:
            updates[field] = val
    for k, v in updates.items():
        set_setting(k, v)
    return {"status": "ok", "updated": list(updates.keys())}


@app.post("/api/shutdown", dependencies=[Depends(verify_api_key)])
def api_shutdown():
    """Graceful shutdown: completes writes, closes DB, stops server."""
    import sys
    threading.Thread(target=lambda: (time.sleep(0.5), sys.exit(0)), daemon=True).start()
    return {"status": "ok", "message": "Shutting down..."}


@app.post("/api/channels", dependencies=[Depends(verify_api_key)])
def api_add_channel(body: ChannelAddRequest):
    try:
        info = resolve_channel(body.url)
        channel_id = add_channel(info)
        process_channel_sync_async(channel_id)
        return {"status": "ok", "channel_id": channel_id, "name": info["name"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/channels", dependencies=[Depends(verify_api_key)])
def api_list_channels() -> list[ChannelResponse]:
    return [ChannelResponse(**ch) for ch in list_channels()]


@app.get("/api/channels/{channel_id}", dependencies=[Depends(verify_api_key)])
def api_get_channel(channel_id: str):
    ch = get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse(**ch)


@app.patch("/api/channels/{channel_id}", dependencies=[Depends(verify_api_key)])
def api_update_channel(channel_id: str, body: ChannelUpdateRequest):
    updates = {}
    if body.auto_update is not None:
        updates["auto_update"] = body.auto_update
    if body.update_interval is not None:
        updates["update_interval"] = body.update_interval
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    ok = update_channel(channel_id, **updates)
    if not ok:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"status": "ok"}


@app.delete("/api/channels/{channel_id}", dependencies=[Depends(verify_api_key)])
def api_delete_channel(channel_id: str):
    ok = delete_channel(channel_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"status": "ok"}


@app.get("/api/channels/{channel_id}/status", dependencies=[Depends(verify_api_key)])
def api_channel_status(channel_id: str):
    status = get_channel_status(channel_id)
    if not status:
        raise HTTPException(status_code=404, detail="Channel not found")
    return status


@app.post("/api/channels/{channel_id}/sync", dependencies=[Depends(verify_api_key)])
def api_sync_channel(channel_id: str):
    ch = get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    process_channel_sync_async(channel_id)
    return {"status": "ok", "message": "Sync started (scan + download)"}


@app.post("/api/channels/{channel_id}/scan", dependencies=[Depends(verify_api_key)])
def api_scan_channel(channel_id: str):
    ch = get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    process_channel_scan_async(channel_id)
    return {"status": "ok", "message": "Scan started"}


@app.post("/api/channels/{channel_id}/download", dependencies=[Depends(verify_api_key)])
def api_download_channel(channel_id: str):
    ch = get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    process_channel_download_async(channel_id)
    return {"status": "ok", "message": "Download started"}


@app.get("/api/channels/{channel_id}/history", dependencies=[Depends(verify_api_key)])
def api_channel_history(channel_id: str):
    history = get_download_history(channel_id)
    return {"channel_id": channel_id, "history": history}


@app.get("/api/channels/{channel_id}/sync/stream")
async def api_sync_stream(channel_id: str, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return StreamingResponse(
        sse_stream(channel_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/channels/{channel_id}/videos", dependencies=[Depends(verify_api_key)])
def api_list_channel_videos(
    channel_id: str,
    last_n: int | None = Query(None),
    days: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[VideoResponse]:
    videos = list_videos(
        channel_id=channel_id,
        last_n=last_n,
        days=days,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [VideoResponse(**{k: v for k, v in vid.items() if k != "caption_text"}) for vid in videos]


@app.get("/api/queue", dependencies=[Depends(verify_api_key)])
def api_download_queue():
    conn = get_db()
    pending = conn.execute("""
        SELECT v.video_id, v.title, v.channel_id, c.name as channel_name
        FROM videos v JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.caption_status IN ('none', 'failed') AND v.never_download = false
        ORDER BY v.publish_date DESC NULLS LAST
        LIMIT 100
    """).fetchall()
    downloaded = conn.execute("""
        SELECT v.video_id, v.title, v.caption_chars, v.caption_lang, v.caption_at, c.name as channel_name
        FROM videos v JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.caption_status = 'downloaded'
        ORDER BY v.caption_at DESC NULLS LAST
        LIMIT 50
    """).fetchall()
    recent = conn.execute("""
        SELECT v.video_id, v.title, v.caption_status, v.last_error, c.name as channel_name
        FROM videos v JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.caption_status IN ('failed', 'unavailable') AND v.never_download = false
        ORDER BY v.updated_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    return {
        "queue": [
            {"video_id": r[0], "title": r[1], "channel": r[3],
             "url": f"https://www.youtube.com/watch?v={r[0]}"}
            for r in pending
        ],
        "recent": [
            {"video_id": r[0], "title": r[1], "chars": r[2], "lang": r[3],
             "at": str(r[4]) if r[4] else None, "channel": r[5],
             "url": f"https://www.youtube.com/watch?v={r[0]}"}
            for r in downloaded
        ],
        "failed": [
            {"video_id": r[0], "title": r[1], "status": r[2], "error": r[3], "channel": r[4],
             "url": f"https://www.youtube.com/watch?v={r[0]}"}
            for r in recent
        ],
    }
def api_list_all_videos(
    status: str | None = Query(None),
    channel_id: str | None = Query(None),
    days: int | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[VideoResponse]:
    videos = list_videos(channel_id=channel_id, days=days, status=status, since=since, limit=limit, offset=offset)
    return [VideoResponse(**{k: v for k, v in vid.items() if k != "caption_text"}) for vid in videos]


@app.post("/api/captions/batch", dependencies=[Depends(verify_api_key)])
def api_batch_captions(body: dict):
    video_ids = body.get("video_ids", [])
    if not isinstance(video_ids, list) or not video_ids:
        raise HTTPException(status_code=400, detail="video_ids must be a non-empty list")
    if len(video_ids) > 100:
        raise HTTPException(status_code=400, detail="Max 100 video_ids per batch request")

    results = []
    for vid in video_ids:
        cap = get_caption(vid)
        if cap:
            results.append(cap)

    return {"captions": results}


@app.post("/api/videos/retry-failed", dependencies=[Depends(verify_api_key)])
def api_retry_failed(body: dict):
    video_ids = body.get("video_ids", [])
    if not isinstance(video_ids, list) or not video_ids:
        raise HTTPException(status_code=400, detail="video_ids required")
    conn = get_db()
    for vid in video_ids:
        conn.execute(
            "UPDATE videos SET caption_status = 'none', retry_count = 0, last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE video_id = ?",
            [vid],
        )
    conn.close()
    return {"status": "ok", "reset": len(video_ids)}


@app.get("/api/videos/{video_id}", dependencies=[Depends(verify_api_key)])
def api_get_video(video_id: str):
    vid = get_video(video_id)
    if not vid:
        raise HTTPException(status_code=404, detail="Video not found")
    return VideoResponse(**{k: v for k, v in vid.items() if k != "caption_text"})


@app.patch("/api/videos/{video_id}", dependencies=[Depends(verify_api_key)])
def api_update_video(video_id: str, body: VideoUpdateRequest):
    updates = {}
    if body.never_download is not None:
        updates["never_download"] = body.never_download
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    ok = update_video(video_id, **updates)
    if not ok:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"status": "ok"}


@app.get("/api/videos/{video_id}/caption", dependencies=[Depends(verify_api_key)])
def api_get_caption(video_id: str, format: str = Query("json")):
    cap = get_caption(video_id)
    if not cap:
        raise HTTPException(status_code=404, detail="Caption not found")

    if format == "txt":
        return PlainTextResponse(cap["text"], media_type="text/plain; charset=utf-8")
    return CaptionResponse(**cap)


@app.post("/api/videos/{video_id}/caption", dependencies=[Depends(verify_api_key)])
def api_redownload_caption(video_id: str):
    vid = get_video(video_id)
    if not vid:
        raise HTTPException(status_code=404, detail="Video not found")

    from app.captions import fetch_caption, RateLimitError
    from app.rate_limiter import rate_limiter
    from datetime import datetime

    try:
        rate_limiter.acquire()
        result, error = fetch_caption(video_id)

        if result:
            update_video(video_id,
                caption_status="downloaded",
                caption_lang=result.language,
                caption_text=result.text,
                caption_chars=len(result.text),
                caption_at=datetime.utcnow().isoformat(),
                last_error=None,
                retry_count=0,
            )
            return {"status": "ok", "chars": len(result.text), "language": result.language}
        elif error == "no_transcript":
            update_video(video_id, caption_status="unavailable", last_error="no_transcript")
            return {"status": "unavailable", "reason": "No transcript available"}
        else:
            update_video(video_id, caption_status="unavailable", last_error=error)
            raise HTTPException(status_code=404, detail=f"Caption unavailable: {error}")

    except RateLimitError as e:
        update_video(video_id, caption_status="failed", last_error="rate_limited",
                    retry_count=(vid["retry_count"] or 0) + 1)
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/videos/{video_id}/caption", dependencies=[Depends(verify_api_key)])
def api_delete_caption(video_id: str):
    ok = delete_caption(video_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Video not found or no caption")
    return {"status": "ok"}
