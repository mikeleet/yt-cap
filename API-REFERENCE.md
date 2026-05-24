# yt-cap API Reference

Base URL: `http://localhost:8000`
Auth: Header `X-API-Key: 12345`

## Health

```
GET /health
```

Returns server status and basic counts. No auth required.

**Response:**
```json
{ "status": "ok", "channels": 3, "videos": 1200, "captions_downloaded": 850 }
```

---

## Channels

### Add Channel

```
POST /api/channels
Content-Type: application/json
```

**Body:**
```json
{ "url": "https://www.youtube.com/@unrealtech/videos" }
```

Accepts: channel URL, video URL, `@handle`, or channel ID (UC...).

**Response:**
```json
{ "status": "ok", "channel_id": "UCeN2YeJcBCRJoXgzF_OU3qw", "name": "Channel Name" }
```

### List Channels

```
GET /api/channels
```

**Response:** Array of channel objects with `channel_id`, `name`, `handle`, `thumbnail_url`, `auto_update`, `update_interval`, `total_videos`, `captions_ok`, `captions_failed`, `last_sync_at`, `sync_status`, `error_message`.

### Get Channel

```
GET /api/channels/{channel_id}
```

### Update Channel

```
PATCH /api/channels/{channel_id}
```

**Body:**
```json
{ "auto_update": false, "update_interval": 43200 }
```

- `auto_update` — boolean, pause/resume background sync
- `update_interval` — seconds between auto-syncs (default: 21600 = 6h)

### Delete Channel

```
DELETE /api/channels/{channel_id}
```

Removes channel and ALL its stored videos/captions.

### Channel Status

```
GET /api/channels/{channel_id}/status
```

**Response:**
```json
{
  "channel_id": "UC...",
  "name": "Channel Name",
  "sync_status": "syncing",
  "total_videos": 874,
  "captions_ok": 142,
  "captions_failed": 3,
  "captions_pending": 726,
  "captions_skipped": 3,
  "last_sync_at": "2026-05-23T10:30:00Z",
  "current_progress": null
}
```

### Trigger Scan

```
POST /api/channels/{channel_id}/scan
```

Scans the channel for videos. **Always works** — no cooldown, no rate limiting. Discovers all videos, updates DB. Does NOT download captions.

### Trigger Caption Download

```
POST /api/channels/{channel_id}/download
```

Downloads captions for pending videos. Respects cooldown from previous rate limits.

### Full Sync (scan + download)

```
POST /api/channels/{channel_id}/sync
```

Convenience: runs scan then download in sequence.

### Sync Progress Stream (SSE)

```
GET /api/channels/{channel_id}/sync/stream
```

Server-Sent Events stream for real-time progress.

**Scan events:**
- `scanning` — discovering videos from YouTube
- `scan_complete` — `{ "total": 874, "new": 5 }`

**Download events:**
- `downloading_start` — `{ "message": "Starting caption download..." }`
- `download_progress` — `{ "pending": 873, "message": "..." }`
- `downloading` — individual video being processed
- `downloaded` — `{ "video_id": "...", "video_title": "...", "chars": 4521, "language": "ko" }`
- `unavailable` — `{ "video_id": "...", "video_title": "...", "reason": "no_transcript" }`
- `rate_limited` — `{ "video_id": "...", "cooldown_seconds": 15 }`
- `cooldown` — cooldown active, download skipped
- `download_complete` — `{ "downloaded": 720, "failed": 6, "cooldown": false }`

---

## Videos

### List Videos by Channel

```
GET /api/channels/{channel_id}/videos
```

**Query params:**
- `last_n` — latest N videos
- `days` — videos from last N days
- `status` — filter: `none`, `downloaded`, `failed`, `unavailable`, `skipped`
- `limit` — max results (default 50, max 500)
- `offset` — pagination offset

### List All Videos (across channels)

```
GET /api/videos
```

**Query params:** `status`, `since` (ISO date, for captions downloaded after), `limit`, `offset`

### Get Video

```
GET /api/videos/{video_id}
```

### Update Video

```
PATCH /api/videos/{video_id}
```

**Body:**
```json
{ "never_download": true }
```

Mark a video as "never download" so the scheduler skips it permanently.

### Get Caption

```
GET /api/videos/{video_id}/caption
GET /api/videos/{video_id}/caption?format=txt
```

- `format=json` (default) — returns `{ video_id, title, language, text, chars }`
- `format=txt` — returns raw text (`text/plain`)

### Batch Get Captions

```
POST /api/captions/batch
```

**Body:**
```json
{"video_ids": ["id1", "id2", "id3"]}
```

Max 100 video_ids per request. Returns only captions that exist (downloaded status).

**Response:**
```json
{
  "captions": [
    {"video_id": "id1", "title": "...", "language": "ko", "text": "...", "chars": 4521}
  ]
}
```

### Redownload Caption

```
POST /api/videos/{video_id}/caption
```

Force re-fetches the caption for this video. Respects rate limiter.

**Response:**
```json
{ "status": "ok", "chars": 4521, "language": "ko" }
```

Returns 429 if rate limited.

### Delete Caption

```
DELETE /api/videos/{video_id}/caption
```

Removes stored caption text. Status resets to `none`.

---

## Settings

### Get Settings

```
GET /api/settings
```

**Response:**
```json
{
  "max_concurrent_fetches": "2",
  "min_interval_seconds": "3",
  "max_per_hour": "100",
  "max_per_day": "500"
}
```

### Update Settings

```
PATCH /api/settings
```

**Body:**
```json
{ "max_per_hour": "50" }
```

All fields optional. Affects future fetches immediately.

---

## Integration Example (RAG Pipeline)

```python
import requests

HEADERS = {"X-API-Key": "12345"}
BASE = "http://ytcap:8000"

# Get all downloaded captions from a channel
r = requests.get(f"{BASE}/api/videos?status=downloaded&limit=500", headers=HEADERS)
videos = r.json()

# Download a specific caption for embedding
for v in videos:
    r = requests.get(f"{BASE}/api/videos/{v['video_id']}/caption?format=txt", headers=HEADERS)
    caption_text = r.text  # raw text, ready for LLM embedding
    # ... add to your vector store ...

# Check for new downloads since last run
r = requests.get(f"{BASE}/api/videos?status=downloaded&since=2026-05-20T00:00:00Z", headers=HEADERS)
new_videos = r.json()
```

## Caption Statuses

| Status | Meaning |
|--------|---------|
| `none` | Not yet attempted |
| `downloaded` | Caption fetched and stored |
| `failed` | Attempted but rate limited (will retry) |
| `unavailable` | No captions exist for this video |
| `skipped` | User marked `never_download` |

## Channel Sync Statuses

| Status | Meaning |
|--------|---------|
| `idle` | Not syncing, waiting for next interval |
| `syncing` | Currently scanning or downloading |
| `paused` | User disabled auto_update |
| `error` | Sync failed (rate limited or other error) |
