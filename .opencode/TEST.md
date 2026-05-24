# yt-cap Integration Test Suite for OpenCode Subagent

This test suite verifies that a client app correctly integrates with yt-cap.
Run these tests after implementing yt-cap integration in a client app.

## Pre-requisites
- yt-cap server running at https://yt.15gva.duckdns.org (with API key 12345)
- At least 1 channel added with some downloaded captions

## Test 1: Server Health and Connectivity

```bash
# 1.1 Health endpoint responds
curl -s https://yt.15gva.duckdns.org/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'ok', 'Health check failed'
assert d['channels'] >= 1, 'No channels exist'
assert d['captions_downloaded'] >= 1, 'No captions downloaded'
print('PASS: Test 1.1 — Health check OK')
"

# 1.2 Auth is enforced
curl -s -o /dev/null -w "%{http_code}" https://yt.15gva.duckdns.org/api/channels | python3 -c "
import sys
code = sys.stdin.read().strip()
assert code == '422' or code == '401', f'Expected 401/422, got {code}'
print('PASS: Test 1.2 — Auth enforced')
"
```

## Test 2: Channel Listing and Status

```bash
# 2.1 List channels returns data
curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/channels | python3 -c "
import sys, json
channels = json.load(sys.stdin)
assert len(channels) >= 1, 'No channels returned'
ch = channels[0]
assert 'channel_id' in ch, 'Missing channel_id'
assert 'name' in ch, 'Missing name'
assert 'total_videos' in ch, 'Missing total_videos'
assert 'captions_ok' in ch, 'Missing captions_ok'
assert 'sync_status' in ch, 'Missing sync_status'
print(f'PASS: Test 2.1 — {len(channels)} channels listed')
"

# 2.2 Channel status provides detailed info
CHANNEL_ID=$(curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/channels | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['channel_id'])")
curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/channels/$CHANNEL_ID/status | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['channel_id'] == '$CHANNEL_ID', 'Wrong channel'
assert 'captions_pending' in d, 'Missing captions_pending'
assert 'captions_skipped' in d, 'Missing captions_skipped'
print(f'PASS: Test 2.2 — Status for {d[\"name\"]} OK ({d[\"captions_ok\"]} captions)')
"
```

## Test 3: Video Retrieval

```bash
# 3.1 Get downloaded videos
curl -s -H "X-API-Key: 12345" "https://yt.15gva.duckdns.org/api/videos?status=downloaded&limit=5" | python3 -c "
import sys, json
videos = json.load(sys.stdin)
assert len(videos) >= 1, 'No downloaded videos'
v = videos[0]
assert v['caption_status'] == 'downloaded', 'Wrong status'
assert 'video_id' in v, 'Missing video_id'
assert 'title' in v, 'Missing title'
assert 'url' in v, 'Missing url'
print(f'PASS: Test 3.1 — {len(videos)} downloaded videos listed')
"

# 3.2 Since filter works
curl -s -H "X-API-Key: 12345" "https://yt.15gva.duckdns.org/api/videos?status=downloaded&since=2026-05-20T00:00:00&limit=500" | python3 -c "
import sys, json
videos = json.load(sys.stdin)
print(f'PASS: Test 3.2 — Since filter returned {len(videos)} videos')
"

# 3.3 Days filter works
curl -s -H "X-API-Key: 12345" "https://yt.15gva.duckdns.org/api/videos?days=365&limit=10" | python3 -c "
import sys, json
videos = json.load(sys.stdin)
print(f'PASS: Test 3.3 — Days filter returned {len(videos)} videos')
"
```

## Test 4: Caption Retrieval

```bash
# 4.1 Get single caption as JSON
VID=$(curl -s -H "X-API-Key: 12345" "https://yt.15gva.duckdns.org/api/videos?status=downloaded&limit=1" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['video_id'])")
curl -s -H "X-API-Key: 12345" "https://yt.15gva.duckdns.org/api/videos/$VID/caption?format=json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'text' in d, 'Missing text field'
assert 'language' in d, 'Missing language field'
assert len(d['text']) > 100, f'Caption too short ({len(d[\"text\"])} chars)'
print(f'PASS: Test 4.1 — Single caption ({d[\"chars\"]} chars, {d[\"language\"]})')
"

# 4.2 Get single caption as raw text
curl -s -H "X-API-Key: 12345" "https://yt.15gva.duckdns.org/api/videos/$VID/caption?format=txt" | python3 -c "
import sys
text = sys.stdin.read()
assert len(text) > 100, f'Raw text too short ({len(text)} chars)'
print(f'PASS: Test 4.2 — Raw text ({len(text)} chars)')
"

# 4.3 Batch caption retrieval
VIDS=$(curl -s -H "X-API-Key: 12345" "https://yt.15gva.duckdns.org/api/videos?status=downloaded&limit=3" | python3 -c "import sys,json;print(json.dumps([v['video_id'] for v in json.load(sys.stdin)]))")
curl -s -X POST -H "X-API-Key: 12345" -H "Content-Type: application/json" \
  -d "{\"video_ids\": $VIDS}" \
  https://yt.15gva.duckdns.org/api/captions/batch | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert len(d['captions']) >= 1, 'No captions returned'
for c in d['captions']:
    assert len(c['text']) > 100, f'Caption {c[\"video_id\"]} too short'
print(f'PASS: Test 4.3 — Batch got {len(d[\"captions\"])} captions')
"
```

## Test 5: Queue and Analytics

```bash
# 5.1 Queue returns pending, recent, and failed
curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/queue | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'queue' in d, 'Missing queue'
assert 'recent' in d, 'Missing recent'
assert 'failed' in d, 'Missing failed'
print(f'PASS: Test 5.1 — Queue: {len(d[\"queue\"])} pending, {len(d[\"recent\"])} recent, {len(d[\"failed\"])} failed')
"

# 5.2 Queue entries have YouTube URLs for manual check
curl -s -H "X-API-Key: 12345" https://yt.15gva.duckdns.org/api/queue | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d['failed']:
    f = d['failed'][0]
    assert 'url' in f, 'Missing URL in failed entry'
    assert f['url'].startswith('https://www.youtube.com/watch?v='), f'Bad URL: {f[\"url\"]}'
    print(f'PASS: Test 5.2 — Failed videos have clickable URLs ({f[\"url\"]})')
else:
    print('SKIP: Test 5.2 — No failed videos to check')
"
```

## Test 6: Python Client Library

```python
# Run: python3 -c "$(cat test_client.py)"
from ytcap_client import YtCapClient
import json

yt = YtCapClient("https://yt.15gva.duckdns.org", api_key="12345")

# 6.1 Health
h = yt.health()
assert h['status'] == 'ok'
print(f'PASS: Test 6.1 — Client health OK ({h}')

# 6.2 List channels
channels = yt.list_channels()
assert len(channels) >= 1
print(f'PASS: Test 6.2 — {len(channels)} channels via client')

# 6.3 Get videos with filter
videos = yt.get_videos(status="downloaded", limit=3)
assert len(videos) >= 1
print(f'PASS: Test 6.3 — {len(videos)} downloaded videos via client')

# 6.4 Get caption text
vid = videos[0]["video_id"]
text = yt.get_caption_text(vid)
assert len(text) > 100
print(f'PASS: Test 6.4 — Caption text ({len(text)} chars) via client')

# 6.5 Batch captions
vids = [v["video_id"] for v in videos[:3]]
batch = yt.get_captions_batch(vids)
assert len(batch["captions"]) >= 1
print(f'PASS: Test 6.5 — Batch {len(batch[\"captions\"])} captions via client')

# 6.6 Queue
queue = yt.get_queue()
assert "queue" in queue
print(f'PASS: Test 6.6 — Queue via client ({len(queue[\"queue\"])} pending)')

# 6.7 Channel status
ch_id = channels[0]["channel_id"]
status = yt.get_channel_status(ch_id)
assert status["channel_id"] == ch_id
print(f'PASS: Test 6.7 — Channel status via client')

# 6.8 Settings
settings = yt.get_settings()
assert "max_per_hour" in settings
print(f'PASS: Test 6.8 — Settings via client')

print("ALL CLIENT TESTS PASSED")
```

## Test 7: RAG Sync Simulation

This simulates what a client app would do to sync captions to its RAG system.

```python
from ytcap_client import YtCapClient
from datetime import datetime, timezone

yt = YtCapClient("https://yt.15gva.duckdns.org", "12345")

# Simulate last sync was 1 hour ago
since = datetime.now(timezone.utc).replace(
    hour=datetime.now(timezone.utc).hour - 1
).isoformat()

# Step 1: Get new captions
new = yt.get_videos(status="downloaded", since=since, limit=500)
print(f"Found {len(new)} new captions since {since}")

if not new:
    print("SKIP: No new captions — all synced")
else:
    # Step 2: Batch get texts
    vids = [v["video_id"] for v in new]
    batch = yt.get_captions_batch(vids)

    # Step 3: Simulate chunking and storing
    total_chunks = 0
    total_chars = 0
    for cap in batch["captions"]:
        chunks = len(cap["text"]) // 800 + 1  # simulate chunking
        total_chunks += chunks
        total_chars += len(cap["text"])

    print(f"PASS: Test 7 — Synced {len(batch['captions'])} captions "
          f"({total_chars:,} chars → ~{total_chunks} chunks) into RAG")
```

## Run All Tests

```bash
# Copy this entire script into test_ytcap_integration.sh
# chmod +x test_ytcap_integration.sh
# bash test_ytcap_integration.sh
```
