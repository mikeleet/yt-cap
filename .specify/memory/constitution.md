# yt-cap Constitution

## Core Principles

### I. Data Integrity (NON-NEGOTIABLE)
- Database must NEVER corrupt. SQLite with WAL mode, thread-local connections, no-op `close()`.
- Single writer via `isolation_level=None` autocommit. No explicit transactions.
- Column order in code MUST match CREATE TABLE column order. No `SELECT *` without validated `cols` list.

### II. Rate Limit Respect
- Site rate-limit: 3-minute cooldown, no API calls during cooldown.
- Health check (`is_rate_limited()`) before resuming any download cycle.
- Exponential backoff only for genuine rate-limits (429, "too many requests"). NOT for generic errors.
- During cooldown: do other work (scan, count, etc.), don't hammer the API.

### III. Scan Efficiency
- First scan: full playlist (all video metadata).
- Subsequent 12hr scans: incremental, 50 most recent videos. Auto-paginate if all 50 are new.
- Publish date comes FREE from caption download page metadata. No separate enrichment API calls.

### IV. Download Integrity
- Only ONE channel downloads at a time (enforced by `sync_status='downloading'` guard).
- Scan during download: must NOT change `sync_status`. Run silently, only add new videos.
- `no_transcript` videos: NOT auto-retried. Manual retry only via API.
- Startup reset: stale `scanning`/`downloading` statuses → `idle`.

### V. Concurrency Safety
- Thread-local DB connections. WAL mode for concurrent reads.
- `_SafeConn` wrapper: `close()` is no-op, `execute()` delegates directly.
- Auto-resume loop: 30s interval, first pass immediate.
- launchd macOS LaunchAgent for auto-start on boot.

### VI. API Design
- `X-API-Key` header for all endpoints.
- Pydantic models with optional fields and sensible defaults (no `NULL` → crash).
- SSE for real-time progress (download/scan events).
- Health endpoint returns counts, no heavy queries.

## Architecture Decisions
- **Playwright** over youtube-transcript-api: more reliable, free metadata.
- **SQLite** over DuckDB: proven multi-thread safety, zero corruption.
- **downloadyoutubesubtitles.com** as caption source: handles rate limits, provides metadata.
- **No Docker** on macOS: launchd for service management, venv for Python isolation.

## Governance
- All changes require: `/speckit.specify` → `/speckit.plan` → `/speckit.analyze` → `/speckit.implement`.
- Bug fixes add: reproduce → root cause → spec before plan.
- Never commit without verifying `curl http://localhost:8506/health` returns 200.

**Version**: 1.0.0 | **Ratified**: 2026-05-24 | **Last Amended**: 2026-05-24
