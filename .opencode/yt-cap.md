# yt-cap — OpenCode Agent Note

You are working on a client app that integrates with **yt-cap**, a self-hosted YouTube caption archive. Use this reference to call yt-cap's API.

## Base URL

Primary: `https://yt.15gva.duckdns.org` (TrueNAS Nginx Proxy → MacBook, PIN: 5580 for UI)
Local: `http://localhost:8506` (direct access, no PIN)

## Authentication
All `/api/*` endpoints need header: `X-API-Key: 12345`

The web UI (`/`, `/ui`) requires PIN `5580` when accessed from non-localhost.
API endpoints are NOT affected by the PIN — only X-API-Key is needed.

## Verify yt-cap is running
```bash
curl -s https://yt.15gva.duckdns.org/health
# {"status":"ok","channels":1,"videos":874,"captions_downloaded":200}
```

## Add a YouTube channel
```bash
curl -s -X POST -H "X-API-Key: 12345" -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/@channelname/videos"}' \
  https://yt.15gva.duckdns.org/api/channels
```

## List all channels with status
```bash
curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/channels
```

## Get channel sync status (with progress)
```bash
curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/channels/{channel_id}/status
```

## Get videos with new captions since a date
```bash
curl -s -H "X-API-Key: 12345" \
  "https://yt.15gva.duckdns.org/api/videos?status=downloaded&since=2026-05-20T00:00:00&limit=500"
```

## Get single caption text (plain text)
```bash
curl -s -H "X-API-Key: 12345" \
  "https://yt.15gva.duckdns.org/api/videos/{video_id}/caption?format=txt"
```

## Batch get captions (up to 100 at once)
```bash
curl -s -X POST -H "X-API-Key: 12345" -H "Content-Type: application/json" \
  -d '{"video_ids":["id1","id2","id3"]}' \
  https://yt.15gva.duckdns.org/api/captions/batch
```

## Get download queue + analytics
```bash
curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/queue
```

## Trigger scan (discover videos — fast, no rate limit)
```bash
curl -s -X POST -H "X-API-Key: 12345" \
  https://yt.15gva.duckdns.org/api/channels/{channel_id}/scan
```

## Trigger caption download
```bash
curl -s -X POST -H "X-API-Key: 12345" \
  https://yt.15gva.duckdns.org/api/channels/{channel_id}/download
```

## Python client library
The file `ytcap_client.py` is a ready-to-use Python client. Copy it to the client app.

```python
from ytcap_client import YtCapClient
yt = YtCapClient("https://yt.15gva.duckdns.org", api_key="12345")

# List channels
channels = yt.list_channels()

# Add a channel (auto-scans on add)
result = yt.add_channel("https://www.youtube.com/@channel/videos")

# Get new captions since last sync
videos = yt.get_videos(status="downloaded", since="2026-05-20T00:00:00")

# Batch get caption text (efficient for RAG)
captions = yt.get_captions_batch([v["video_id"] for v in videos])

# Trigger download
yt.download_channel("UC...")

# Check health
health = yt.health()
```

## Key Integration Patterns

### Pattern 1: RAG Sync (Periodic)
1. `GET /api/videos?status=downloaded&since={last_sync}` → get new video IDs
2. `POST /api/captions/batch {"video_ids": [...]}` → get all caption texts at once
3. Chunk each caption text → embed → store in vector DB
4. Update `last_sync` timestamp

### Pattern 2: Channel Management
1. `GET /api/channels` → list all channels with status
2. `POST /api/channels {"url": "..."}` → add new channel
3. `GET /api/channels/{id}/status` → detailed progress

### Pattern 3: Auto-Sync
- yt-cap auto-resumes downloads every 10 seconds for channels with `auto_update=true`
- Cooldowns are 15s→30s→60s→max 300s
- No need for client to re-trigger constantly

## Video Status Reference

| Status | Meaning |
|--------|---------|
| `none` | Not yet attempted |
| `downloaded` | Caption fetched and stored |
| `failed` | Rate limited (will retry automatically) |
| `unavailable` | No captions exist for this video |
| `skipped` | User marked `never_download` |

## Channel Sync Statuses

| Status | Meaning |
|--------|---------|
| `idle` | Waiting for next interval or manual trigger |
| `scanning` | Discovering videos from YouTube |
| `downloading` | Downloading captions for pending videos |
| `error` | Rate limited or other error (auto-recovers) |
| `paused` | User disabled `auto_update` |

## Important: Data Persistence
- All data is in DuckDB (`data/ytcap.db`)
- Survives server restarts and crashes
- Channel status, progress, and captions all persist
