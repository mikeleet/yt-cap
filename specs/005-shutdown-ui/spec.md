# Feature Specification: Graceful Shutdown Button

**Feature Branch**: `005-shutdown-ui`

**Created**: 2026-05-24

**Input**: "add shutdown button in UI, so that we can safely shutdown without corrupting db"

## User Story 1 - Safe Shutdown (Priority: P1)

User clicks "Shutdown" in the web UI. Server stops gracefully: completes current write, closes DB connections, exits cleanly. No DB corruption.

**Acceptance Scenarios**:
1. **Given** server is downloading, **When** user clicks Shutdown, **Then** server completes current write, closes DB, stops
2. **Given** server is idle, **When** user clicks Shutdown, **Then** server stops immediately with no errors

## Requirements
- **FR-001**: `POST /api/shutdown` endpoint (protected by X-API-Key)
- **FR-002**: Shutdown button in UI navbar (red, requires confirmation)
- **FR-003**: Server exits with code 0, launchd auto-restarts (KeepAlive)
