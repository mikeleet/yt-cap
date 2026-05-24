# Feature Specification: Chunked Video Scanning

**Feature Branch**: `002-chunked-scan`

**Created**: 2026-05-24

**Status**: Implemented

**Input**: "sometimes there are channels with 1000s of videos, should we call in chunks too?"

## User Scenarios & Testing

### User Story 1 - Add Large Channel Without Timeout (Priority: P1)

When a user adds a YouTube channel with 1000+ videos, the initial scan should NOT fail with a timeout or rate-limit error. Instead, it should fetch videos in manageable chunks.

**Why this priority**: Without chunking, channels with many videos cause yt-dlp to timeout (120s subprocess limit) or hit YouTube rate limits. Adding a popular channel like @MrBeast (800+ videos) should work reliably.

**Independent Test**: Add a channel with 500+ videos. Verify scan completes without timeout and all videos appear in the database.

**Acceptance Scenarios**:
1. **Given** a channel with 874 videos, **When** initial scan runs, **Then** videos are fetched in 200-video chunks (5 calls), all 874 videos stored
2. **Given** a channel with 2400 videos, **When** initial scan runs, **Then** videos are fetched in 200-video chunks (12 calls), no timeout
3. **Given** a channel with 50 videos, **When** initial scan runs, **Then** single chunk of 50, stops when batch < 200

### User Story 2 - Chunk Rate Limiting (Priority: P1)

Between each scan chunk, there must be a delay to avoid triggering YouTube's rate limit.

**Why this priority**: Making 5-25 rapid yt-dlp calls in succession will trigger YouTube rate limits, blocking subsequent caption downloads.

**Independent Test**: Scan a large channel and verify no rate-limit errors occur during or immediately after the scan.

**Acceptance Scenarios**:
1. **Given** a full scan with 5 chunks, **When** chunks execute, **Then** there is a 5-second delay between each chunk
2. **Given** an incremental scan (50 videos, single chunk), **When** scan runs, **Then** no delay (only one chunk, no rate limit risk)

### Edge Cases

- yt-dlp fails on first chunk → `RuntimeError` raised (no partial data)
- yt-dlp fails on subsequent chunk (offset > 0) → breaks loop, returns videos collected so far
- Empty channel (0 videos) → single chunk returns empty, loop breaks immediately
- Playlist with exactly chunk_size videos → fetches full batch, next chunk returns fewer → breaks

## Requirements

### Functional Requirements

- **FR-001**: System MUST split full scans into 200-video chunks using `--playlist-start`/`--playlist-end`
- **FR-002**: System MUST split incremental scans into 50-video chunks
- **FR-003**: System MUST insert 5-second delay between scan chunks (except first)
- **FR-004**: System MUST break the chunk loop when `len(batch) < chunk_size` (last page reached)
- **FR-005**: System MUST return all collected videos from successful chunks even if later chunk fails

## Success Criteria

- **SC-001**: Channel with 874 videos completes full scan in under 30 seconds (5 chunks × 5s delay + yt-dlp time)
- **SC-002**: Channel with 5000 videos completes without timeout or rate limit
- **SC-003**: No rate-limit errors on caption downloads immediately following a full scan

## Assumptions

- yt-dlp `--flat-playlist --playlist-start N --playlist-end M` is supported by yt-dlp >= 2024
- YouTube returns videos sorted newest-first (playlist order)
- 5-second delay between chunks is sufficient to avoid YouTube rate limiting
- 200 videos per chunk is a safe balance between speed and API load
