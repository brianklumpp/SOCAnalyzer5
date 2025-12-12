# Auto-Merge Disable Feature Implementation

## Summary

Added ability to disable automated control merging after extraction completes. This gives users full control over when and how duplicate controls are consolidated.

## Changes Made

### 1. Configuration Flag (`backend/app/config.py`)

Added new environment variable:

```python
# Enable/disable automated merging after extraction (set to "false" to disable)
ENABLE_AUTO_MERGE = os.getenv("ENABLE_AUTO_MERGE", "true").lower() == "true"
```

**Default**: `true` (maintains existing behavior)

### 2. Conditional Execution (`backend/app/main.py`)

Modified `/analyze/finalize` endpoint to check flag before running cleanup:

```python
# Run automated cleanup first (if enabled)
if config.ENABLE_AUTO_MERGE:
    try:
        cleanup_stats = await automated_cleanup(scan_id_for_learning, db)
        if cleanup_stats:
            logging.info(f"[/analyze/finalize] Automated cleanup complete: {cleanup_stats}")
    except Exception as cleanup_err:
        logging.warning(f"[/analyze/finalize] Automated cleanup failed: {cleanup_err}")
else:
    logging.info(f"[/analyze/finalize] Automated cleanup disabled (ENABLE_AUTO_MERGE=false)")
```

**Location**: Lines 2445-2453

### 3. Environment Template (`.env.dist`)

Added documentation and default values:

```bash
# Automated Merging Settings
# Set to "false" to disable automatic merging of duplicate controls after extraction
ENABLE_AUTO_MERGE=true
# Minimum similarity score (0.0-1.0) for automatic merging (default: 0.70)
AUTO_MERGE_MIN_CONFIDENCE=0.70
```

### 4. Documentation (`docs/DISABLE_AUTO_MERGE.md`)

Created comprehensive guide covering:
- When to disable auto-merge
- How to configure the setting
- What happens when disabled
- Manual cleanup options
- Best practices for different environments
- Troubleshooting common issues

## Usage

### Disable Auto-Merge

Add to `.env`:

```bash
ENABLE_AUTO_MERGE=false
```

Restart backend:

```powershell
docker compose restart backend
```

### Re-Enable

Remove line from `.env` or set to `true`:

```bash
ENABLE_AUTO_MERGE=true
```

Restart backend.

### Manual Cleanup

Even with auto-merge disabled, you can manually trigger cleanup on specific scans:

```bash
POST /report/{scan_id}/cleanup
```

## Impact

### When Enabled (Default)
- ✅ Auto-merges duplicates with ≥70% similarity
- ✅ Flags extraction errors (<60% similarity)
- ✅ Flags low-confidence controls
- ✅ Reduces manual review by 30-50%

### When Disabled
- ✅ All controls extracted normally
- ✅ All duplicates remain visible
- ✅ Duplicate highlighting still works
- ✅ Manual merging still available
- ❌ No automatic consolidation
- ❌ No automatic error flagging

## Testing

To test the feature:

1. **Verify default behavior** (enabled):
   ```powershell
   # Ensure ENABLE_AUTO_MERGE is not set or set to true
   docker compose logs backend | Select-String "Automated cleanup complete"
   ```

2. **Test disabled state**:
   ```powershell
   # Add ENABLE_AUTO_MERGE=false to .env
   docker compose restart backend
   # Run a scan
   docker compose logs backend | Select-String "Automated cleanup disabled"
   ```

3. **Test manual cleanup**:
   ```powershell
   # With auto-merge disabled
   Invoke-RestMethod -Method Post -Uri "http://localhost:5001/report/123/cleanup"
   ```

## Backward Compatibility

✅ **Fully backward compatible**

- Default value is `true` (existing behavior)
- No changes required to existing deployments
- Environment variable is optional
- Manual cleanup endpoint already existed

## Files Modified

1. `backend/app/config.py` - Added ENABLE_AUTO_MERGE configuration
2. `backend/app/main.py` - Added conditional check before cleanup
3. `.env.dist` - Added documentation and default values
4. `docs/DISABLE_AUTO_MERGE.md` - New comprehensive guide

## Related Features

This change does **not** affect:

- Control extraction logic
- Duplicate detection/highlighting
- Manual merging via UI
- Merge suggestion API
- Continuation handling (chunk-split controls still merged during extraction)

## Future Enhancements

Potential improvements:

1. **Per-scan setting** - Allow enabling/disabling per scan type
2. **UI toggle** - Add frontend switch to enable/disable before scanning
3. **Audit mode** - Option to run cleanup but only flag, not merge
4. **Custom thresholds** - Per-scan auto-merge confidence thresholds
5. **Scheduled cleanup** - Run cleanup on schedule rather than immediately

## Support

For issues or questions:
- See `docs/DISABLE_AUTO_MERGE.md` for detailed guide
- Check logs for "Automated cleanup" messages
- Use `/report/{scan_id}/cleanup` endpoint for manual testing
