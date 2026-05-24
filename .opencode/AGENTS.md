# yt-cap — Spec-Driven Development (AUTOMATIC)

## CRITICAL: Every code change MUST follow this workflow.

You are an opencode agent. When the user asks for ANY feature, fix, or change, you **MUST** go through the spec-kit pipeline. Do NOT skip steps. Do NOT ask permission — just do it.

### Workflow (automatic)

| When user says... | You automatically do... |
|---|---|
| "Fix X bug" or "X is broken" | `/speckit.specify` (document the bug + expected fix) → `/speckit.plan` → `/speckit.implement` |
| "Add X feature" or "Can you X" | `/speckit.specify` (user story + requirements) → `/speckit.clarify` (if ambiguous) → `/speckit.plan` → `/speckit.analyze` → `/speckit.implement` |
| "Change X" or "Update Y" | `/speckit.specify` → `/speckit.plan` → `/speckit.implement` |
| General discussion or question | Answer directly. No spec needed unless code changes. |

### How to execute each step

1. **`/speckit.specify`** — Read `.specify/templates/spec-template.md` first. Write the spec in `specs/NNN-feature-name/spec.md`. Include user stories, acceptance criteria, functional requirements, edge cases.
2. **`/speckit.clarify`** — If anything is ambiguous, ask the user structured questions. Don't guess.
3. **`/speckit.plan`** — Read `.specify/templates/plan-template.md`. Write `specs/NNN-feature-name/plan.md` with tech stack, affected files, data model changes, API changes.
4. **`/speckit.analyze`** — Cross-check spec vs plan for consistency, missing edge cases, DB safety, rate limit compliance.
5. **`/speckit.implement`** — Make the code changes. After changes: `rm -rf app/__pycache__`, restart launchd, verify health.

### After any implementation
```bash
curl -s http://localhost:8506/health        # Must return 200
curl -s -H "x-api-key: 12345" http://localhost:8506/api/channels  # Must return valid JSON
```

## Project Rules (from constitution)

1. **DB = SQLite, never close connections** — `_SafeConn.close()` is no-op. WAL mode. Thread-local.
2. **Rate limits = 3-min cooldown** — Site-specified wait if available. No API calls during cooldown.
3. **Scan = incremental after first** — Full playlist on first scan, 50 most recent after. Auto-paginate if all new.
4. **Metadata = from caption page** — publish_date + duration come FREE with caption download. No separate enrichment.
5. **One download at a time** — Guarded by `sync_status='downloading'` check in both auto-resume and download function.
6. **Scan during download = silent** — Don't change sync_status. Just add new videos to DB.
7. **`no_transcript` = no auto-retry** — Manual retry only. Filtered from pending count with `NOT LIKE 'no_transcript%'`.
8. **Column order = exact match** — `SELECT *` must have matching `cols` list in code. Check `PRAGMA table_info()` if unsure.

## Key Files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, auto-resume loop, lifespan, API endpoints |
| `app/scheduler.py` | scan, download, cooldown, rate limiting, SSE events |
| `app/captions.py` | Playwright → downloadyoutubesubtitles.com caption fetch |
| `app/db.py` | SQLite `_SafeConn` wrapper, thread-local, WAL |
| `app/channel.py` | Channel CRUD, yt-dlp integration |
| `app/video.py` | Video CRUD, upsert |
| `app/sse.py` | Server-Sent Events for UI progress |
| `app/rate_limiter.py` | Per-process rate limiter |
| `app/models.py` | Pydantic models (all Optional with defaults) |
| `app/index.html` | Vue.js SPA web UI |

## Testing
- **Always** clear cache: `rm -rf app/__pycache__` before restart
- Restart: `launchctl bootout gui/$(id -u)/com.ytcap.server; sleep 2; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ytcap.server.plist`
- Verify: `curl -s http://localhost:8506/health`

### QA Gate (MANDATORY before handoff)

After EVERY implementation, run the QA test suite from `specs/007-qa-testing/spec.md`. Minimum:

```bash
# Health + Channels + Queue must return valid JSON
curl -s http://localhost:8506/health | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'"
curl -s -H "x-api-key: 12345" http://localhost:8506/api/channels | python3 -c "import sys,json; assert len(json.load(sys.stdin))>=1"
curl -s -H "x-api-key: 12345" http://localhost:8506/api/queue | python3 -c "import sys,json; assert 'queue' in json.load(sys.stdin)"

# Download must actually change caption count (proves rate_limiter import, DB writes, Playwright)
BEFORE=$(curl -s -H "x-api-key: 12345" http://localhost:8506/api/channels | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['captions_ok'])")
sleep 10
AFTER=$(curl -s -H "x-api-key: 12345" http://localhost:8506/api/channels | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['captions_ok'])")
python3 -c "assert $AFTER >= $BEFORE, 'Download not progressing'"

# No bug-induced errors in DB (catches import renames, function renames)
python3 -c "
import sqlite3
db = sqlite3.connect('data/ytcap.db')
bad = db.execute(\"SELECT COUNT(*) FROM videos WHERE caption_status='unavailable' AND (last_error LIKE '%not defined%' OR last_error LIKE '%NameError%' OR last_error LIKE '%ImportError%')\").fetchone()[0]
assert bad == 0, f'{bad} videos have bug errors'
db.close()
"
```

If ANY test fails, do NOT hand off. Fix the issue, re-run ALL tests.
