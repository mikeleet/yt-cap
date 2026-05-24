# yt-cap — YouTube Caption Archive

Self-hosted YouTube caption archiver. Subscribe to channels, auto-download closed captions, and expose them via API for RAG / LLM pipelines.

**No API keys. No YouTube login. Just captions.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## What It Does

1. **Add a YouTube channel** by URL — yt-dlp discovers all videos
2. **Auto-downloads captions** via downloadyoutubesubtitles.com (Playwright headless)
3. **Stores everything** in SQLite — captions, metadata, video info
4. **Serves a web dashboard** — real-time progress via SSE, search, export
5. **Exposes a REST API** — fetch captions individually or in batch (for RAG/LLM)

```bash
# Add a channel
curl -X POST -H "x-api-key: 12345" \
  -d '{"url":"https://www.youtube.com/@3Blue1Brown"}' \
  http://localhost:8506/api/channels

# Get captions
curl -H "x-api-key: 12345" \
  http://localhost:8506/api/videos/dQw4w9WgXcQ/caption
```

## Features

| Feature | Detail |
|---|---|
| **Channel scanning** | Full + incremental (chunked for large channels) |
| **Auto-download** | Background thread, resumes after restart, one channel at a time |
| **Rate limit handling** | Centralized cooldown manager. 3-min global cooldown, per-chunk delays |
| **Web UI** | Vue.js SPA with SSE real-time progress, queue view, settings panel |
| **API** | REST + SSE. X-API-Key auth. Batch caption retrieval |
| **DB** | SQLite with WAL mode, thread-local connections, write serialization |
| **Service** | macOS LaunchAgent (auto-start on boot). `yt-cap.sh` for start/stop/status |
| **SDD** | spec-kit workflow — spec → plan → implement → QA gate |

## Quick Start (macOS Local)

```bash
# 1. Clone
git clone https://github.com/mikeleet/yt-cap.git
cd yt-cap

# 2. Install
bash yt-cap.sh start
# Creates .venv, installs deps, launches server on :8506

# 3. Open UI
open http://localhost:8506
# PIN is 5580 (for non-localhost access)

# 4. Add a channel
# Use the UI or API to add YouTube channels

# 5. Install as service (auto-start on boot)
bash yt-cap.sh install
```

## Docker (Alternative)

```bash
cp .env.example .env
bash docker-run.sh
```

## Architecture

```
╔══════════════════════════════════════════╗
║              Web UI (Vue.js)            ║
║         SSE ← real-time progress        ║
╠══════════════════════════════════════════╣
║           FastAPI REST API              ║
║    /api/channels  /api/videos           ║
║    /api/queue     /api/settings         ║
╠══════════════════════════════════════════╣
║  Auto-Resume Thread (30s loop)          ║
║  ├── Scan scheduler                     ║
║  ├── Download scheduler                 ║
║  └── Rate limit manager                 ║
╠══════════════════════════════════════════╣
║  Caption Fetcher (Playwright headless)  ║
║  → downloadyoutubesubtitles.com         ║
╠══════════════════════════════════════════╣
║  yt-dlp  │  SQLite (WAL)  │  LaunchAgent║
╚══════════════════════════════════════════╝
```

### Key Files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, auto-resume loop, API endpoints |
| `app/scheduler.py` | Scan, download, rate limiting, SSE events |
| `app/captions.py` | Playwright → downloadyoutubesubtitles.com |
| `app/db.py` | SQLite _SafeConn (thread-local, write-serialized) |
| `app/ratelimit.py` | Centralized cooldown manager |
| `app/channel.py` | Channel CRUD + yt-dlp |
| `app/video.py` | Video CRUD + upsert |
| `app/rate_limiter.py` | Per-process download rate limiter |
| `app/models.py` | Pydantic models |
| `app/sse.py` | Server-Sent Events |
| `app/index.html` | Vue.js SPA (single-file) |

## API

All `/api/*` endpoints require `X-API-Key` header (default: `12345`).

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/channels` | Add channel by YouTube URL |
| GET | `/api/channels` | List all channels with status |
| POST | `/api/channels/{id}/scan` | Trigger full scan |
| POST | `/api/channels/{id}/download` | Start caption download |
| POST | `/api/channels/{id}/sync` | Scan + download |
| GET | `/api/channels/{id}/sync/stream` | SSE progress stream |
| GET | `/api/channels/{id}/videos` | List channel videos |
| GET | `/api/videos/{id}` | Get video details |
| GET | `/api/videos/{id}/caption` | Get caption (JSON or TXT) |
| POST | `/api/videos/{id}/caption` | Re-download single caption |
| POST | `/api/captions/batch` | Batch fetch captions |
| POST | `/api/videos/retry-failed` | Requeue failed videos |
| GET | `/api/queue` | Download queue + stats |
| GET/PATCH | `/api/settings` | Rate limit config |
| POST | `/api/shutdown` | Graceful shutdown |
| GET | `/health` | Health check (no auth) |

Full docs: [API-REFERENCE.md](API-REFERENCE.md)

## Rate Limiting

The centralized `app/ratelimit.py` manager coordinates cooldowns between scanning and downloading:

- **3-minute cooldown** when any operation hits a rate limit (shared across all operations)
- **10s interval** between caption downloads (configurable)
- **3s delay** between scan chunks, waits for cooldown if active
- **200/hr, 5000/day** caps (configurable via API)

When rate-limited, ALL operations (scan + download) pause until cooldown expires.

## Spec-Driven Development

This project uses [spec-kit](https://github.com/github/spec-kit) for specification-driven development. Every feature goes through:

```
/speckit.specify → /speckit.plan → /speckit.analyze → /speckit.implement
```

All specs live in `specs/`. The constitution is in `.specify/memory/constitution.md`.

## QA Gate

Before any deliverable, the QA test suite in `specs/007-qa-testing/spec.md` must pass:

1. Health endpoint returns 200
2. Channels/Queue endpoints return valid JSON
3. Download trigger actually downloads captions
4. No bug-induced errors in DB (e.g., import rename → NameError)

## License

MIT — see [LICENSE](LICENSE)
