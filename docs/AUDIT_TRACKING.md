# Audit Tracking Feature

## Overview

All updates to Controls, CUECs, and Subservice Organizations are now tracked with:
- **Who** made the change (user or system)
- **When** the change was made

## Database Fields

### New Columns (All Tables: control, cuec, subservice_org)

- `updated_at` (timestamp): When the record was last modified
- `updated_by_user_id` (integer, FK to users.id): Which user made the update
  - `NULL` = System/automated update
  - `<user_id>` = User who made the update

## API Response

All PATCH endpoints now return:
```json
{
  "id": 123,
  // ... other fields ...
  "updated_at": "2025-12-19T07:22:14.081025",
  "updated_by": "bklumpp"  // or "System" for automated updates
}
```

## User Updates

When a user edits a record via the UI:
- `updated_at` = current timestamp
- `updated_by_user_id` = current user's ID
- `edit_log` = appended with timestamp and change description

**Example edit_log entry:**
```
UI edit: confidence 0.85 -> 0.92 (2025-12-19 07:22 PM)
```

## System Updates

When the system automatically modifies a record (e.g., automated cleanup, merges):
- `updated_at` = current timestamp
- `updated_by_user_id` = `NULL`
- `edit_log` = appended with `[SYSTEM]` prefix

**Example edit_log entry:**
```
[SYSTEM] Extraction error flagged - missing control_id (2025-12-19 07:22 PM)
```

## Implementation Details

### Utility Functions

Located in `backend/app/utils/audit.py`:

```python
from backend.app.utils.audit import mark_system_update, mark_user_update

# For automated/system updates
mark_system_update(control, "Automated cleanup - duplicate merged")

# For user updates (usually handled automatically by routers)
mark_user_update(control, user_id, "Manual confidence adjustment")
```

### Router Updates

All PATCH endpoints automatically populate audit fields:
- `/report/{scan_id}/controls/id/{control_db_id}`
- `/report/{scan_id}/cuecs/{cuec_id}`
- `/report/{scan_id}/suborgs/id/{suborg_id}`

### Migration

Migration: `20251219_add_audit_tracking_to_cuec_suborg`

Run with:
```bash
docker-compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

## Use Cases

### Track Who Changed a Control
Query the database:
```sql
SELECT 
    c.control_id,
    c.control_desc,
    c.updated_at,
    u.username as updated_by
FROM control c
LEFT JOIN users u ON c.updated_by_user_id = u.id
WHERE c.scan_id = 123
ORDER BY c.updated_at DESC;
```

### Find All System Updates
```sql
SELECT * FROM control 
WHERE updated_at IS NOT NULL 
  AND updated_by_user_id IS NULL
ORDER BY updated_at DESC;
```

### Find Records Changed by Specific User
```sql
SELECT * FROM control c
JOIN users u ON c.updated_by_user_id = u.id
WHERE u.username = 'bklumpp'
ORDER BY c.updated_at DESC;
```

## Frontend Display

The frontend can now display:
- "Last updated by **bklumpp** on 12/19/2025 7:22 PM"
- "Last updated by **System** on 12/19/2025 7:22 PM"

Extract from API response:
```typescript
const { updated_at, updated_by } = controlData;
if (updated_at) {
  console.log(`Last updated by ${updated_by || 'Unknown'} at ${updated_at}`);
}
```

## Future Enhancements

- Add `created_at` and `created_by_user_id` for tracking record creation
- Track field-level changes (which specific fields were modified)
- Audit trail table for complete change history
- Retention policy for old audit records
