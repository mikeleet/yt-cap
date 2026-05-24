# Feature Specification: Scan Chunk Progress & Delay

**Feature Branch**: `003-scan-progress`

**Created**: 2026-05-24

**Input**: "wait 10 seconds for each chunk call, show chunk progression in scanning, indicate full scan or incremental scan"

## User Scenarios

### User Story 1 - Chunk Progress Visibility (Priority: P1)

During a scan, the UI should show which chunk is being processed (e.g., "Scanning chunk 3/5, 200 videos each"). For incremental scans, show "Incremental scan" vs "Full scan".

**Acceptance Scenarios**:
1. **Given** a full scan of 874 videos (5 chunks of 200), **When** scanning chunk 3, **Then** UI shows "Full scan – chunk 3/5"
2. **Given** an incremental scan (1 chunk of 50), **When** scanning, **Then** UI shows "Incremental scan – chunk 1"
3. **Given** a full scan of 50 videos (1 chunk), **When** scanning, **Then** UI shows "Full scan – chunk 1/1"

### User Story 2 - 10-Second Chunk Rate Limit (Priority: P1)

Between scan chunks, wait 10 seconds (not 5) to ensure YouTube rate limits are respected.

**Acceptance Scenarios**:
1. **Given** a scan with 3 chunks, **When** chunk 1 completes, **Then** wait 10 seconds before chunk 2

## Requirements

- **FR-001**: SSE events during scan MUST include `scan_type` ("full" or "incremental"), `chunk_current`, and `chunk_total`
- **FR-002**: Chunk delay MUST be 10 seconds between calls
- **FR-003**: First chunk MUST report total chunks (playlist_count / chunk_size, rounded up) via SSE
