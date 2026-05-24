# yt-cap — YouTube Caption Archive

A self-hosted tool for archiving YouTube video captions. Add channels, auto-download subtitles, query via API.

**No API keys. No YouTube account. Just captions.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## Motivation

I built this to feed Korean tech YouTube captions into an LLM RAG pipeline. Manually downloading subtitles from hundreds of videos was painful, so yt-cap automates the whole thing — channel discovery, caption fetching, rate limiting, and API access.

## What It Does

- **Discovers videos** from any YouTube channel via yt-dlp
- **Downloads captions** through downloadyoutubesubtitles.com using headless Chromium (Playwright)
- **Stores everything** in SQLite — full text, metadata, language info
- **Web dashboard** with real-time progress, video browser, queue view
- **REST API** for integration with other tools (RAG pipelines, research apps)

```bash
# Add a channel
curl -X POST -H "x-api-key: 12345" \
  -d '{"url":"https://www.youtube.com/@3Blue1Brown"}' \
  http://localhost:8506/api/channels

# Fetch a caption
curl -H "x-api-key: 12345" \
  http://localhost:8506/api/videos/dQw4w9WgXcQ/caption
```

## Quick Start

```bash
git clone https://github.com/mikeleet/yt-cap.git
cd yt-cap
bash yt-cap.sh start
# Opens on http://localhost:8506 (PIN: 5580)
```

To run on boot (macOS):
```bash
bash yt-cap.sh install   # LaunchAgent, auto-starts on login
```

Docker alternative:
```bash
cp .env.example .env && bash docker-run.sh
```

## Architecture

```
┌─────────────────────────────────────────────┐
│  Vue.js SPA           SSE ← live progress  │
├─────────────────────────────────────────────┤
│  FastAPI              REST + auth           │
├─────────────────────────────────────────────┤
│  Background thread (30s loop)               │
│  ├─ Scan scheduler    (yt-dlp chunks)       │
│  ├─ Download queue    (one-at-a-time)       │
│  └─ Rate limiter      (shared cooldowns)    │
├─────────────────────────────────────────────┤
│  Caption fetcher      Playwright headless   │
│  → downloadyoutubesubtitles.com             │
├─────────────────────────────────────────────┤
│  yt-dlp  │  SQLite (WAL)  │  LaunchAgent    │
└─────────────────────────────────────────────┘
```

### Key Files

| File | What |
|---|---|
| `app/main.py` | App entry, auto-resume loop, all endpoints |
| `app/scheduler.py` | Video scanning, caption downloads, cooldowns |
| `app/captions.py` | Playwright browser automation for the download site |
| `app/db.py` | SQLite with thread-local connections and write serialization |
| `app/ratelimit.py` | Shared cooldown manager for scan + download |
| `app/rate_limiter.py` | Per-call rate limiter (interval, hourly/daily caps) |
| `app/channel.py` | Channel CRUD, yt-dlp integration |
| `app/video.py` | Video CRUD |
| `app/models.py` | Pydantic request/response schemas |
| `app/sse.py` | Server-Sent Events for UI progress |
| `app/index.html` | Vue.js single-file SPA |

## API Reference

Default API key: `12345`. All `/api/*` endpoints require `X-API-Key` header.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/channels` | Add a YouTube channel |
| GET | `/api/channels` | List channels with status/progress |
| POST | `/api/channels/{id}/scan` | Trigger video discovery |
| POST | `/api/channels/{id}/download` | Start caption download |
| POST | `/api/channels/{id}/sync` | Scan then download |
| GET | `/api/channels/{id}/sync/stream` | SSE progress stream |
| GET | `/api/channels/{id}/videos` | Channel video list (filterable) |
| GET | `/api/videos/{id}/caption` | Caption as JSON or plain text |
| POST | `/api/videos/{id}/caption` | Re-fetch single caption |
| POST | `/api/captions/batch` | Batch fetch multiple captions |
| POST | `/api/videos/retry-failed` | Requeue failed videos |
| GET | `/api/queue` | Pending/recent/failed videos |
| GET/PATCH | `/api/settings` | Rate limit configuration |
| POST | `/api/shutdown` | Graceful server shutdown |
| GET | `/health` | Quick health check (no auth) |

### Integration Example

Use yt-cap as a caption provider for a RAG app:

```python
import requests

HEADERS = {"x-api-key": "12345"}
BASE = "http://localhost:8506"

# Get recent captions
resp = requests.get(f"{BASE}/api/queue", headers=HEADERS)
data = resp.json()
# data["recent"] has downloaded captions with video_id, title, chars, lang, url

# Bulk fetch caption text
ids = [r["video_id"] for r in data["recent"]]
resp = requests.post(f"{BASE}/api/captions/batch", json={"video_ids": ids}, headers=HEADERS)
captions = resp.json()["captions"]  # list of {video_id, title, language, text, chars}
```

See `ytcap_client.py` for a Python client wrapper.

## Rate Limiting

Rate limits are shared between scanning and downloading via a central manager (`app/ratelimit.py`). When either operation hits a limit, both pause for the cooldown period.

- **3-minute cooldown** on rate-limit detection
- **10s interval** between caption fetches (adjustable)
- **3s delay** between yt-dlp scan chunks
- Caps: 200/hr, 5000/day (adjustable via API settings)

## Database

SQLite with WAL journal mode for concurrent read/write safety. Thread-local connections serialize writes through a global lock — single-writer, multi-reader. The `_SafeConn` wrapper prevents accidental connection closure across threads.

Video metadata (publish date, duration) is extracted for free from the download site's page — no extra API calls needed.

## Known Limitations

- Playwright-based caption fetching means ~1 caption/minute (browser overhead + rate limits)
- Single-machine design — SQLite isn't distributed
- English + Korean languages tested primarily; others should work
- Requires macOS for LaunchAgent; Docker available for Linux

## License

MIT
