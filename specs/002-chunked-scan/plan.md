# Implementation Plan: Chunked Video Scanning

**Branch**: `002-chunked-scan` | **Date**: 2026-05-24 | **Spec**: `specs/002-chunked-scan/spec.md`

## Summary

Replace single-shot yt-dlp scan with chunked pagination: 200 videos per chunk for full scans, 50 for incremental. 5-second delay between chunks prevents rate limiting.

## Technical Context

- **Language/Version**: Python 3.11
- **Primary Dependencies**: yt-dlp (subprocess), SQLite
- **Storage**: SQLite `videos` table
- **Target Platform**: macOS server (launchd)

## Changes

### File: `app/scheduler.py` — `scan_channel_videos()`

**Before**: Single `subprocess.run(yt-dlp)` call fetching all videos. Incremental mode used `--playlist-end` with manual offset.

**After**: While loop with chunked pagination:
- `chunk_size = 50` (incremental) or `200` (full)
- Loop: build `--playlist-start/--playlist-end`, run yt-dlp, collect videos, increment offset
- Break when `len(batch) < chunk_size` (last page)
- 5-second `_time.sleep()` between chunks (after first)
- First chunk failure → `RuntimeError` (no data at all)
- Subsequent chunk failure → break (return partial data)

### File: `app/scheduler.py` — `process_channel_scan()`

**Before**: Manual while loop with `offset` parameter. Checked if all 50 incrementals were new to auto-paginate.

**After**: Single call to `scan_channel_videos(incremental=...)` — pagination handled internally. Removed offset-based pagination logic.

## Verification

```bash
# Add a large channel
curl -X POST -H "x-api-key: 12345" -d '{"url":"https://youtube.com/@LargeChannel"}' \
  http://localhost:8506/api/channels

# Check all videos discovered
curl -H "x-api-key: 12345" http://localhost:8506/api/channels
```
