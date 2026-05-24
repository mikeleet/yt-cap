# yt-cap — YouTube Caption Archive

Self-hosted YouTube caption archiver. Subscribe to channels, auto-download closed captions, and expose them via API for RAG / LLM pipelines.

Runs as a single Docker container. No external API keys needed. Data lives in one DuckDB file.

## Quick Start (Docker)

```bash
cp .env.example .env
bash docker-run.sh
```

Or manually:
```bash
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:8506` for the UI.

## Quick Start (macOS — no Docker)

```bash
# After AirDrop, fix permissions:
bash fix-permissions.sh

# Then launch:
bash start.sh
```

Or double-click `yt-cap.app`.

## Data Persistence

Everything lives in `data/ytcap.db`. Mount the `data/` directory as a Docker volume. Backup = copy the file.

## API

See [API-REFERENCE.md](API-REFERENCE.md) for full documentation.

Authentication via `X-API-Key` header. Default: `12345`. Override with `YTCAP_API_KEY` env var.

## Features

- Subscribe/unsubscribe YouTube channels by URL or handle
- Auto-scan: periodically discovers new videos (every 12h)
- Auto-downloads closed captions via Playwright (handles website rate limits)
- Rate limiting: configurable interval, hourly/daily caps
- Pause/resume auto-update per channel
- Per-video: view, download, redownload, delete caption, mark "skip"
- REST API for external consumption (RAG pipelines)
- Batch caption retrieval for efficient client sync
- Single-page UI with Vue 3 (self-hosted, no CDN dependency)
- PIN-protected remote access

## Architecture

| Layer | Technology |
|-------|-----------|
| Server | FastAPI + uvicorn |
| Database | DuckDB (single file) |
| Captions | Playwright → downloadyoutubesubtitles.com |
| Metadata | yt-dlp |
| UI | Vue 3 (self-hosted) |
| Container | Single Docker image |
