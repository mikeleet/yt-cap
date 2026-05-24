# Feature Specification: Centralized Rate Limit Manager

**Feature Branch**: `006-rate-limit-manager`

**Created**: 2026-05-24

**Input**: "since scanning and downloading both affect rate limit there should be rate limit management module which provides cools time for everyone"

## User Story 1 - Unified Cooldown (Priority: P1)

When either scanning or downloading hits a rate limit, ALL YouTube/download site operations are blocked for the cooldown period. This prevents one operation from using up the rate limit budget and starving the other.

**Acceptance Scenarios**:
1. **Given** download hits rate limit with 3-min cooldown, **When** scan tries to start, **Then** scan waits for cooldown to expire
2. **Given** scan is running in chunks, **When** a chunk hits rate limit, **Then** remaining chunks wait and download is also blocked
3. **Given** cooldown expires, **When** health check passes, **Then** both scan and download can resume

## User Story 2 - Pre-Flight Check (Priority: P1)

Before any expensive API call (yt-dlp chunk, Playwright browser launch), the system checks the centralized rate limit manager.

**Acceptance Scenarios**:
1. **Given** cooldown is active, **When** any API call is attempted, **Then** call is skipped with log message
2. **Given** no cooldown, **When** API call is made, **Then** call proceeds normally

## Requirements

- **FR-001**: RateLimitManager MUST be a module-level singleton (`app/ratelimit.py`)
- **FR-002**: `can_proceed()` → False if any cooldown is active
- **FR-003**: `set_cooldown(seconds)` → blocks all operations for N seconds
- **FR-004**: `is_healthy()` → quick API check that cooldown has really expired
- **FR-005**: Both `scheduler.py` (scan+download) and `captions.py` (health check) MUST use the manager
- **FR-006**: Deprecate old `RETRY_COOLDOWN` and `get_cooldown`/`set_cooldown` in scheduler.py
