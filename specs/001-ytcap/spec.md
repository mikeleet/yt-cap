# yt-cap — Specification

## Overview
Self-hosted YouTube caption archive. Discovers videos from channels, downloads captions via downloadyoutubesubtitles.com, stores in SQLite, serves via FastAPI + Web UI.

## User Stories

### US1 — Add YouTube Channel
As a user, I want to add a YouTube channel by URL so its videos are discovered and captions archived.

**Acceptance**: POST `/api/channels` with `{"url": "https://www.youtube.com/@handle"}` returns channel_id. Channel auto-scans immediately. UI shows "scanning" then "idle" or "downloading".

### US2 — Automatic Video Discovery
As a user, I want videos to be automatically discovered from added channels so I don't need to manually list them.

**Acceptance**: On channel add: full scan via yt-dlp flat-playlist. Every 12 hours: incremental scan (50 most recent). New videos get `caption_status='none'`. UI shows total_videos count.

### US3 — Automatic Caption Download
As a user, I want captions to download automatically after video discovery so I have a searchable archive.

**Acceptance**: Auto-resume loop picks up channels with pending videos. Downloads via downloadyoutubesubtitles.com (Playwright headless). Rate-limited: 3-min cooldown. UI shows done/total progress, per-video SSE events.

### US4 — Rate Limit Handling
As a system, I must respect the download site's rate limits so downloads don't get blocked.

**Acceptance**: "Please allow your previous download" → immediate cooldown using site's specified wait time. Generic rate-limit → 3-min fixed cooldown. Health check before resuming. During cooldown, skip ALL API calls.

### US5 — Web Dashboard
As a user, I want to see channel status, download progress, and video list in a browser.

**Acceptance**: `/` serves Vue.js SPA (PIN-protected for non-localhost). Shows channels with status badges, progress bars, download queue, recent activity, SSE real-time updates.

### US6 — Caption Retrieval API
As a developer, I want to fetch captions via API for integration with other tools.

**Acceptance**: `GET /api/videos/{id}/caption` returns JSON or plain text. `POST /api/captions/batch` returns multiple captions at once. `GET /api/queue` shows pending/downloaded/failed videos.

### US7 — Manual Controls
As a user, I want to manually scan, download, retry, or skip videos.

**Acceptance**: Buttons for scan/download per channel. Retry failed videos. "Skip" toggle (never_download). Delete caption. View/download caption text. All via API + UI.

## Functional Requirements

### FR1 — Channel Management
- Add channel: POST `/api/channels` with YouTube URL
- List channels: GET `/api/channels` with status, counts, progress
- Update: PATCH `/api/channels/{id}` (auto_update, update_interval)
- Delete: DELETE `/api/channels/{id}` (cascade: all videos deleted)

### FR2 — Video Discovery (Scan)
- yt-dlp `--flat-playlist --dump-json` for full scans
- yt-dlp `--playlist-end 50` for incremental scans
- Auto-paginate if all 50 are new (offset += 1)
- Upsert video: update title/url/thumbnail, preserve caption data
- Publish_date enrichment: FREE from caption download page, not separate API

### FR3 — Caption Download
- Playwright headless Chromium → downloadyoutubesubtitles.com
- Click TXT button, handle download event
- Extract: text, language code, publish_date, duration_sec
- "There is no subtitle" → `caption_status='unavailable'`, `last_error='no_transcript:...'`
- "Please allow your previous download" → RateLimitError with site cooldown
- Rate_limiter: 10s min interval, 200/hr max, 5000/day max (adjustable via API)

### FR4 — Auto-Resume Loop
- Daemon thread, runs every 30s (first pass: immediate)
- Queries channels where `auto_update=true`
- Stuck detection: "downloading" 2 cycles unchanged → reset to "idle"
- Stuck detection: "scanning" 2 cycles → reset to "idle"
- Scan trigger: `last_scan_at` NULL or elapsed >= update_interval
- Download trigger: no cooldown, pending videos exist, no other channel downloading
- Rate limit check: `is_rate_limited()` before starting any download

### FR5 — Concurrency
- ONLY one channel downloads at a time (guard in download function + auto-resume)
- Scan during download: run silently, don't change sync_status
- DB: thread-local SQLite with WAL mode, no-op close()
- Multiple readers, single writer serialized via SQLite's internal WAL

### FR6 — Server Management
- macOS LaunchAgent (com.ytcap.server) for auto-start on boot
- start.sh: finds Python 3.11+, creates venv, installs deps, launches uvicorn
- Health: GET `/health` → channel/video/caption counts
- Logs: stdout/stderr → data/ytcap.log

## Data Model

### channels
| Column | Type | Notes |
|---|---|---|
| channel_id | TEXT PK | YouTube channel ID |
| name | TEXT | Channel display name |
| handle | TEXT | @handle |
| auto_update | INTEGER | 0/1 |
| update_interval | INTEGER | seconds, default 43200 (12h) |
| sync_status | TEXT | idle/scanning/downloading/error |
| current_video_id | TEXT | video being downloaded |
| progress_done/total | INTEGER | download progress |
| current_phase | TEXT | browser_launch/page_load |

### videos
| Column | Type | Notes |
|---|---|---|
| video_id | TEXT PK | YouTube video ID |
| caption_status | TEXT | none/downloaded/failed/unavailable |
| caption_text | TEXT | raw caption text |
| caption_lang | TEXT | ko/en/ja/etc |
| caption_chars | INTEGER | text length |
| never_download | INTEGER | 0/1, skip toggle |
| retry_count | INTEGER | auto-retries before giving up |
| last_error | TEXT | error reason |
| publish_date | TEXT | from caption page metadata |
| duration_sec | INTEGER | from caption page metadata |

## API Reference

See `API-REFERENCE.md` for full endpoint documentation.

## Edge Cases

1. **Empty channel**: 0 videos, status stays "idle"
2. **No subtitles**: marked "unavailable" with exact reason from site
3. **Rate limit during scan**: scan cooldown, retried next loop
4. **Server crash mid-download**: startup reset clears stale statuses
5. **yt-dlp failure**: RuntimeError caught, channel stays "idle"
6. **DB locked**: WAL mode handles concurrent access, busy_timeout=5s
7. **Playwright crash**: browser closed in finally block, RateLimitError raised
8. **New channel with 50+ uploads**: auto-paginates until previously-scanned video found
