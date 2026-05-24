# yt-cap → Client App Integration Guide

## Overview

yt-cap is your central YouTube caption archive. Client apps query it via REST API instead of downloading captions themselves. yt-cap handles all rate limiting, retries, Playwright browser management, and storage.

**Service URL**: `https://yt.15gva.duckdns.org` (TrueNAS Nginx Proxy Manager → local MacBook)
**Local fallback**: `http://localhost:8506`

## Quick Start (Client App)

### 1. Copy the client library

```bash
cp ytcap_client.py /path/to/your/app/
```

### 2. Install dependency

```bash
pip install httpx
```

### 3. Add config

In `.env`:
```
YTCAP_URL=https://yt.15gva.duckdns.org
YTCAP_API_KEY=12345
```

### 4. Start coding

```python
from ytcap_client import YtCapClient

yt = YtCapClient("https://yt.15gva.duckdns.org", api_key="12345")

# Always verify server is reachable
health = yt.health()
print(f"Server: {health['channels']} channels, {health['captions_downloaded']} captions")
```

---

## Pattern 1: Sync New Captions to RAG

This is the most common pattern for RAG-based apps. Run periodically to pull new captions since last sync.

```python
from ytcap_client import YtCapClient
import time
from datetime import datetime, timezone

yt = YtCapClient("https://yt.15gva.duckdns.org", "12345")

# Track your last sync time (store in DB or file)
LAST_SYNC_FILE = "data/last_ytcap_sync.txt"

def load_last_sync():
    try:
        with open(LAST_SYNC_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "2020-01-01T00:00:00"  # first run: get everything

def save_last_sync():
    with open(LAST_SYNC_FILE, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())

def sync_captions_to_rag(rag_manager):
    """Pull new captions from yt-cap and add to your RAG."""
    since = load_last_sync()

    # Step 1: Get all newly downloaded captions
    videos = yt.get_videos(status="downloaded", since=since, limit=500)
    print(f"Found {len(videos)} new captions since {since}")

    if not videos:
        print("Nothing new to sync")
        return

    # Step 2: Batch-fetch caption text (more efficient than one-by-one)
    video_ids = [v["video_id"] for v in videos]
    batch = yt.get_captions_batch(video_ids)

    # Step 3: Chunk and store in your RAG
    for cap in batch["captions"]:
        # Your chunking logic here
        chunks = chunk_text(cap["text"], chunk_size=800, overlap=100)

        for i, chunk in enumerate(chunks):
            rag_manager.add_document(
                text=chunk,
                metadata={
                    "source": "youtube",
                    "video_id": cap["video_id"],
                    "title": cap["title"],
                    "channel": cap.get("channel", ""),
                    "chunk_index": i,
                }
            )

    # Step 4: Update last sync time
    save_last_sync()
    print(f"Synced {len(batch['captions'])} captions to RAG")
```

---

## Pattern 2: Add a Channel

```python
def subscribe_channel(youtube_url):
    """Add a new channel to yt-cap and start tracking it."""
    # Step 1: Add to yt-cap (auto-resolves channel info, auto-scans)
    result = yt.add_channel(youtube_url)
    channel_id = result["channel_id"]
    channel_name = result["name"]
    print(f"Added: {channel_name} ({channel_id})")

    # Step 2: Register in your own DB
    your_db.register_youtube_channel(
        channel_id=channel_id,
        name=channel_name,
        url=youtube_url,
        ytcap_managed=True,  # flag: captions come from yt-cap
    )

    # Step 3: Optional - trigger full download immediately
    # yt.download_channel(channel_id)

    return channel_id
```

---

## Pattern 3: Channel Dashboard

Show users which channels are available and their status.

```python
def get_channel_dashboard():
    """Return a summary of all yt-cap channels for UI display."""
    channels = yt.list_channels()

    dashboard = []
    for ch in channels:
        dashboard.append({
            "id": ch["channel_id"],
            "name": ch["name"],
            "handle": ch.get("handle", ""),
            "total_videos": ch["total_videos"],
            "captions_ok": ch["captions_ok"],
            "captions_failed": ch["captions_failed"],
            "sync_status": ch["sync_status"],
            "last_scan": ch.get("last_scan_at"),
            "last_download": ch.get("last_download_at"),
            "progress": ch.get("current_progress"),  # active download info
        })

    return dashboard
```

---

## Pattern 4: Manual Video Check

```python
def check_failed_video(video_id):
    """Check why a specific video failed and get its YouTube link."""
    video = yt.get_video(video_id)
    return {
        "title": video["title"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "status": video["caption_status"],
        "error": video.get("last_error"),
        "retries": video.get("retry_count"),
    }
```

---

## Pattern 5: Health Monitoring

```python
def monitor_health():
    """Periodic health check."""
    health = yt.health()

    issues = []
    if health["channels"] == 0:
        issues.append("No channels subscribed")

    queue = yt.get_queue()
    if queue["failed"]:
        issues.append(f"{len(queue['failed'])} videos failed")

    # Check each channel status
    for ch in yt.list_channels():
        if ch["sync_status"] == "error":
            issues.append(f"Channel {ch['name']} in error state: {ch.get('error_message')}")

    return {
        "healthy": len(issues) == 0,
        "issues": issues,
        "stats": health,
        "queue": len(queue["queue"]),
    }
```

---

## API Cheat Sheet

| What you want | Endpoint | Method |
|--------------|----------|--------|
| List all channels | `/api/channels` | GET |
| Add channel by URL | `/api/channels` | POST `{"url": "..."}` |
| Channel sync status | `/api/channels/{id}/status` | GET |
| Scan for new videos | `/api/channels/{id}/scan` | POST |
| Download captions | `/api/channels/{id}/download` | POST |
| Get new captions | `/api/videos?status=downloaded&since=ISO` | GET |
| Get caption text | `/api/videos/{id}/caption?format=txt` | GET |
| Batch get captions | `/api/captions/batch` | POST `{"video_ids": [...]}` |
| Download queue | `/api/queue` | GET |
| Server health | `/health` | GET |
| Mark video skip | `/api/videos/{id}` | PATCH `{"never_download": true}` |
| Delete caption | `/api/videos/{id}/caption` | DELETE |

---

## Deployment

Both yt-cap and your client app run on the same machine:

```
MacBook Pro M1 16GB
├── yt-cap server (port 8506 → yt.15gva.duckdns.org)  ~100MB idle, ~500MB peak
├── invest-research (port 8504)  ~2-3GB (ChromaDB + LLM)
└── Other apps

### Docker Compose (both apps together)

```yaml
services:
  ytcap:
    build: /path/to/yt-cap
    ports:
      - "8506:8506"
    volumes:
      - /path/to/ytcap-data:/app/data
    environment:
      - YTCAP_API_KEY=12345
    restart: unless-stopped

  invest-research:
    build: /path/to/invest-research
    ports:
      - "8504:8504"
    volumes:
      - /path/to/invest-data:/app/data
    environment:
      - YTCAP_URL=https://yt.15gva.duckdns.org
      - YTCAP_API_KEY=12345
    restart: unless-stopped
```

### Docker Compose (both apps together)

```yaml
services:
  ytcap:
    build: /path/to/yt-cap
    ports:
      - "8506:8506"
    volumes:
      - /path/to/ytcap-data:/app/data
    environment:
      - YTCAP_API_KEY=12345
    restart: unless-stopped

  invest-research:
    build: /path/to/invest-research
    ports:
      - "8504:8504"
    volumes:
      - /path/to/invest-data:/app/data
    environment:
      - YTCAP_URL=http://ytcap:8506
      - YTCAP_API_KEY=12345
    depends_on:
      - ytcap
    restart: unless-stopped
```
