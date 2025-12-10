# Redis & WebSockets

## Overview

Redis serves as the caching and job tracking layer, while WebSockets provide real-time updates to the frontend.

## Redis Configuration

- **Container**: socanalyzer-redis
- **Version**: Redis 7 Alpine
- **Port**: 6379 (internal only)
- **Persistence**: None (ephemeral cache)

## Use Cases

### Job Tracking
Redis stores analysis job state during PDF processing:
- Job ID → Progress percentage
- Extractor status (pending, running, complete)
- Error messages
- Control counts
- Line-based progress tracking

### Caching
- Help content caching
- Frequently accessed data
- Session data

### Pub/Sub
Real-time event broadcasting for:
- Progress updates
- Extractor completion
- Error notifications

## WebSocket Integration

### Socket.IO Server
Backend WebSocket server (`backend/app/main.py`):
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Real-time updates for scan progress
```

### Client Connection
Frontend connection (`src/pages/AnalyzerPage.tsx`):
- Connects on scan start
- Receives progress updates
- Updates UI in real-time
- Disconnects on completion

### Events
- `progress`: Percentage complete
- `extractor_status`: Individual extractor updates
- `counts`: Running totals (controls, CUECs, etc.)
- `error`: Extraction errors

## Data Structure

### Job State
```json
{
  "job_id": "uuid",
  "progress": 75,
  "done": false,
  "error": null,
  "checklist": [
    {"name": "controls", "status": "complete"},
    {"name": "cuec", "status": "running"}
  ],
  "counts": {
    "control": 45,
    "cuec": 12,
    "subservice_org": 3
  }
}
```

### Line Progress
```json
{
  "controls": {
    "current_line": 1500,
    "end_line": 2000,
    "percent_complete": 75
  }
}
```

## Performance Benefits

- **Reduced Database Load**: Frequent progress checks hit Redis, not PostgreSQL
- **Fast Updates**: Sub-millisecond response times
- **Scalability**: Handles multiple concurrent scans
- **Real-time UX**: Immediate feedback without polling

## Connection Management

Redis connections are managed via connection pools:
- Async Redis for FastAPI endpoints
- Sync Redis for background tasks
- Automatic reconnection on failure
