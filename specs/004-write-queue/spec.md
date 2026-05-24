# Feature Specification: Write Queue

**Feature Branch**: `004-write-queue`

**Created**: 2026-05-24

**Input**: "only 1 write process at time, there should be write queue management"

## User Story 1 - Single Writer Guarantee (Priority: P1)

All database writes (INSERT/UPDATE/DELETE) must be serialized through a single queue. Multiple readers can run concurrently. This prevents any possibility of write conflicts even under heavy load.

**Acceptance Scenarios**:
1. **Given** download thread is writing video status, **When** auto-resume thread tries to write channel status, **Then** second write waits for first to complete
2. **Given** 3 concurrent writes queued, **When** each completes, **Then** they execute in order, no "database is locked" errors

## Requirements

- **FR-001**: `_SafeConn.execute()` MUST detect write SQL and serialize via queue
- **FR-002**: Read queries (SELECT) MUST NOT go through the queue
- **FR-003**: Write queue MUST be FIFO
