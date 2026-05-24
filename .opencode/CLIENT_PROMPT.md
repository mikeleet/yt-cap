# Prompt for OpenCode Agent — yt-cap Client Integration

Copy the text below and paste it into OpenCode when working on a client app
that needs to integrate with yt-cap (like app-04-invest-research).

---

## Agent Prompt

```
You are working on app-04-invest-research at /Users/mike/Documents/GitHub/non_sn/app-04-invest-research.

This app currently has its own YouTube channel manager (youtube_channel_manager.py)
that downloads captions directly from YouTube. We are migrating it to use yt-cap
as the central caption provider.

yt-cap is a self-hosted YouTube caption archive running at:
  https://yt.15gva.duckdns.org (TrueNAS Nginx Proxy Manager → local MacBook)
  http://localhost:8506 (local fallback)
(API key: 12345). The UI is PIN-protected (PIN: 5580) for non-localhost access.
The API uses X-API-Key: 12345 header for all endpoints. It handles all YouTube interaction — channel scanning, caption
downloads, rate limiting, retries, and Playwright browser management.

## Your Tasks

### 1. Study the existing codebase
Read these files to understand the current YouTube integration:
- youtube_channel_manager.py — how channels are synced, transcripts downloaded
- youtube_manager.py — how transcripts are fetched for chat
- database.py — youtube_channels and yt_videos tables
- server.py — WebSocket actions (list_channels, add_channel, sync_channel, etc.)
- rag_manager.py — how captions are chunked and stored in ChromaDB

### 2. Integrate yt-cap client
Copy the client library from:
/Users/mike/Documents/GitHub/non_sn/app-06-youtube_knowledge/ytcap_client.py
into the invest-research app directory.

Read these reference files:
- /Users/mike/Documents/GitHub/non_sn/app-06-youtube_knowledge/INTEGRATION.md
- /Users/mike/Documents/GitHub/non_sn/app-06-youtube_knowledge/API-REFERENCE.md
- /Users/mike/Documents/GitHub/non_sn/app-06-youtube_knowledge/.opencode/yt-cap.md

### 3. Implement the following features

#### 3.1 Add yt-cap config
Add to .env:
YTCAP_URL=https://yt.15gva.duckdns.org
YTCAP_API_KEY=12345

#### 3.2 Replace direct YouTube downloads with yt-cap
Modify youtube_channel_manager.py:
- Keep the existing sync_channel function as a fallback
- Add a new function sync_from_ytcap() that:
  a. Gets list of channels from yt-cap via GET /api/channels
  b. For each channel, gets new captions via GET /api/videos?status=downloaded&since={last_sync}
  c. Batch-fetches caption text via POST /api/captions/batch
  d. Chunks text (800 words, 100 overlap) and stores in ChromaDB
  e. Records processed video IDs in SQLite yt_videos table
  f. Updates last_sync timestamp

#### 3.3 Replace direct transcript download with yt-cap
Modify youtube_manager.py:
- Change get_transcript() to fetch from yt-cap instead of youtube-transcript-api
- Use yt.get_caption_text(video_id) which returns raw text
- Handle missing captions gracefully (return None instead of crashing)

#### 3.4 Add WebSocket actions for yt-cap integration
In server.py, add these new WebSocket action handlers:
- ytcap_channels — list all yt-cap channels with status (call yt.list_channels())
- ytcap_add_channel — add a channel by URL (call yt.add_channel())
- ytcap_sync_rag — pull new captions from yt-cap and sync to local RAG
- ytcap_queue — show download queue and analytics from yt-cap
- ytcap_health — verify yt-cap is running (call yt.health())

Each action should send progress updates via WebSocket so the UI shows real-time status.

#### 3.5 Update the database schema
In database.py, add to youtube_channels table:
- ytcap_managed BOOLEAN DEFAULT 1 — whether captions come from yt-cap
- ytcap_last_sync TIMESTAMP — last time we synced from yt-cap

In yt_videos table:
- source TEXT DEFAULT 'direct' — 'direct' or 'ytcap'

#### 3.6 Update the frontend
In static/index.html, add to the YouTube section:
- Show yt-cap connection status (green dot if healthy)
- List yt-cap channels with status badges (idle, downloading, error)
- Show captions_ok / total_videos for each channel
- "Sync to RAG" button per channel or globally
- Progress bar when syncing
- Add channel form that sends to yt-cap

#### 3.7 Run the test suite
After implementing, run the tests from:
/Users/mike/Documents/GitHub/non_sn/app-06-youtube_knowledge/.opencode/TEST.md

Verify:
- yt-cap health check passes
- Channel listing works
- Caption retrieval works (single + batch)
- RAG sync simulation works
- Client library methods all work

### 4. Important Notes

- yt-cap handles all rate limiting. Do NOT add additional rate limiting on the client side.
- yt-cap auto-resumes downloads every 10 seconds for channels with auto_update=true.
  Do NOT implement a polling loop — just sync periodically (every 6 hours or on manual trigger).
- Caption text from yt-cap is raw plain text. Chunk it before storing in ChromaDB.
- Keep the existing direct download code as a fallback, but prefer yt-cap.
- All yt-cap API calls need X-API-Key: 12345 header.
- The batch endpoint (POST /api/captions/batch) is the most efficient way to get captions.
- yt-cap is available at https://yt.15gva.duckdns.org (or http://localhost:8506 locally).

### 5. Expected Outcome

When done, the invest-research app should:
- Show yt-cap channels and their sync status in the UI
- Let users add YouTube channels (which go to yt-cap)
- Periodically sync new captions from yt-cap to the local ChromaDB RAG
- Use yt-cap caption text in chat research (replacing direct youtube-transcript-api calls)
- Work even if yt-cap is temporarily unavailable (graceful degradation)

### 6. Testing Locally

Before starting, verify yt-cap is running:
curl -sk https://yt.15gva.duckdns.org/health
# Should show channels and captions_downloaded counts
```
