# QA Testing Checklist

**Purpose**: Run before delivering any code change to the user. Catches regressions like import renames, function name mismatches, DB schema drift.

**Status**: Required before every `/speckit.implement` completion.

## Pre-Flight (5 seconds)

```bash
# 1. Server alive & returns valid JSON
curl -s http://localhost:8506/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok', 'health failed'"

# 2. Channels endpoint returns valid JSON
curl -s -H "x-api-key: 12345" http://localhost:8506/api/channels | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d)>=1, 'no channels'"

# 3. Queue endpoint returns valid JSON
curl -s -H "x-api-key: 12345" http://localhost:8506/api/queue | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'queue' in d, 'queue broken'"
```

## Functional (30 seconds)

```bash
# 4. Download trigger works (returns 200, status changes)
BEFORE=$(curl -s -H "x-api-key: 12345" http://localhost:8506/api/channels | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['captions_ok'])")
curl -s -X POST -H "x-api-key: 12345" http://localhost:8506/api/channels/UCeN2YeJcBCRJoXgzF_OU3qw/download
sleep 5
AFTER=$(curl -s -H "x-api-key: 12345" http://localhost:8506/api/channels | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['captions_ok'])")
python3 -c "assert $AFTER >= $BEFORE, f'download not progressing: $BEFORE -> $AFTER'"
echo "Download progressing OK"

# 5. Scan trigger works
curl -s -X POST -H "x-api-key: 12345" http://localhost:8506/api/channels/UCeN2YeJcBCRJoXgzF_OU3qw/scan | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'"
echo "Scan trigger OK"

# 6. Settings endpoint works
curl -s -H "x-api-key: 12345" http://localhost:8506/api/settings | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'min_interval_seconds' in d"
echo "Settings OK"

# 7. Shutdown endpoint exists
curl -s -X POST -H "x-api-key: 12345" http://localhost:8506/api/shutdown
# (server will restart via launchd KeepAlive)
sleep 8
curl -s http://localhost:8506/health | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'"
echo "Shutdown/restart OK"
```

## Data Integrity (10 seconds)

```bash
# 8. No videos incorrectly marked unavailable
sqlite3 /Users/Shared/myapp_installed/app-06-youtube_knowledge/data/ytcap.db \
  "SELECT last_error, COUNT(*) FROM videos WHERE caption_status='unavailable' GROUP BY last_error" \
  | grep -i "not defined\|NameError\|ImportError" && echo "FAIL: bug-induced errors found" || echo "OK"
```

## UI Integrity

- Visit `http://localhost:8506/`
- Verify channel list shows both channels with correct video counts
- Verify "Download" button is clickable without JS errors
- Verify "Scan" button is clickable without JS errors
- Check browser console for errors (F12 → Console)
- Verify "Queue" tab shows pending videos
- Verify "Activity" tab shows download events

## Common Regressions This Catches

| Bug | Caught by |
|---|---|
| Import renamed but usage not updated (`rate_limiter` → `download_rate_limiter`) | Test #4 |
| Function renamed but caller not updated (`remaining` → `cooldown_remaining`) | Test #2 |
| Missing `global` declaration causing UnboundLocalError | Test #1 |
| `.isoformat()` on SQLite strings instead of datetime objects | Test #3 |
| Schema column order mismatch | Test #2 |
| Auto-resume not starting downloads | Test #4 |
| Cooldown stuck (timer not resetting) | Test #4 |
