# Disabling Automated Control Merging

## Overview

By default, SOCAnalyzer automatically merges duplicate controls after extraction completes. This feature uses AI to detect duplicates based on similarity scores and automatically merges controls with ≥70% similarity.

## When to Disable Auto-Merge

You may want to disable automated merging if:

- **Manual review preferred** - You want to manually review all duplicates before merging
- **Testing/debugging** - You want to see all extracted controls without automatic consolidation
- **Quality assurance** - You need to audit the extraction quality before any merging occurs
- **Custom workflows** - Your process requires inspection before any data consolidation

## How to Disable

### Option 1: Environment Variable (Recommended)

Add to your `.env` file:

```bash
ENABLE_AUTO_MERGE=false
```

### Option 2: Docker Compose

Add to your `docker-compose.yml` backend service:

```yaml
services:
  backend:
    environment:
      - ENABLE_AUTO_MERGE=false
```

### Option 3: Per-Deployment Configuration

For distribution deployments, edit the `.env` file in the extracted distribution folder before running `IMPORT.ps1`.

## What Happens When Disabled

When `ENABLE_AUTO_MERGE=false`:

1. ✅ **Controls are extracted normally** - All control extraction runs as usual
2. ✅ **Duplicates are visible** - All duplicate controls remain in the database
3. ✅ **Duplicate highlighting works** - Frontend still highlights duplicates with colored badges
4. ✅ **Manual merging available** - You can still merge controls manually via the UI
5. ❌ **No automatic merging** - System won't auto-merge high-similarity duplicates
6. ❌ **No extraction error flagging** - Low-similarity duplicates won't be automatically flagged

### Log Output

When disabled, you'll see in the logs:

```
[/analyze/finalize] Automated cleanup disabled (ENABLE_AUTO_MERGE=false)
```

When enabled (default):

```
[/analyze/finalize] Automated cleanup complete: {'extraction_errors_flagged': 3, 'controls_auto_merged': 12, ...}
```

## Re-Enabling Auto-Merge

To re-enable automated merging:

1. Set `ENABLE_AUTO_MERGE=true` in `.env` (or remove the line to use default)
2. Restart backend: `docker compose restart backend`
3. Run cleanup manually on existing scans: `POST /report/{scan_id}/cleanup`

## Manual Cleanup

You can manually trigger automated cleanup on a scan even when auto-merge is disabled:

```bash
# Via API
curl -X POST http://localhost:5001/report/{scan_id}/cleanup

# Via PowerShell
Invoke-RestMethod -Method Post -Uri "http://localhost:5001/report/{scan_id}/cleanup"
```

This is useful for:
- Testing cleanup on specific scans
- Running cleanup after changing `AUTO_MERGE_MIN_CONFIDENCE` threshold
- Re-processing scans after reviewing extraction quality

## Automated Cleanup Details

When enabled, `automated_cleanup()` performs:

### 1. Extraction Error Flagging

Flags controls with issues:
- Blank control IDs
- Duplicate control IDs with low similarity (<60%)

**Action**: Reduces confidence score and adds notes to `confidence_calc`

### 2. High-Confidence Auto-Merge

Automatically merges duplicates with ≥70% similarity:
- Keeps the highest confidence instance as primary
- Merges others into primary
- Records merge history in `merge_history` column

**Result**: Reduces manual review burden by 30-50%

### 3. Low-Confidence Flagging

Flags low-quality extractions:
- CUECs with confidence <50%
- Subservice orgs with confidence <40%

**Action**: Adds quality notes to help with review

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_AUTO_MERGE` | `true` | Enable/disable automated merging |
| `AUTO_MERGE_MIN_CONFIDENCE` | `0.70` | Minimum similarity for auto-merge (0.0-1.0) |
| `MERGE_SUGGESTION_MIN_CONFIDENCE` | `0.50` | Minimum similarity for manual merge suggestions |
| `MERGE_SUGGESTION_MAX_RESULTS` | `50` | Max merge suggestions to return |

## Troubleshooting

### "Too many duplicates remaining"

If you're getting too many duplicate controls even with auto-merge enabled:

1. **Lower the threshold** - Try `AUTO_MERGE_MIN_CONFIDENCE=0.65`
2. **Check similarity scores** - Use the merge suggestions UI to see actual scores
3. **Review extraction quality** - Check if controls are being extracted properly

### "Controls are being merged incorrectly"

If incorrect controls are being merged:

1. **Raise the threshold** - Try `AUTO_MERGE_MIN_CONFIDENCE=0.80`
2. **Disable auto-merge** - Set `ENABLE_AUTO_MERGE=false` and merge manually
3. **Review merge history** - Check `control.merge_history` to see merge decisions

### "I disabled auto-merge but scans are still merging"

Check:
1. Environment variable is set correctly: `echo $env:ENABLE_AUTO_MERGE` (PowerShell)
2. Backend has been restarted: `docker compose restart backend`
3. You're not manually triggering `/cleanup` endpoint

## Best Practices

### Development/Testing

```bash
ENABLE_AUTO_MERGE=false  # Review all extracted controls
QUICK_TEST_MODE=true     # Faster testing with limited controls
```

### Quality Assurance

```bash
ENABLE_AUTO_MERGE=false              # Manual review first
AUTO_MERGE_MIN_CONFIDENCE=0.80       # Conservative when enabled
```

### Production

```bash
ENABLE_AUTO_MERGE=true               # Reduce manual workload
AUTO_MERGE_MIN_CONFIDENCE=0.70       # Balanced threshold
```

## Related Features

- **Duplicate Highlighting** - Visual indicators for duplicate controls (always enabled)
- **Merge Suggestions** - AI-powered suggestions for manual merging (always available)
- **Batch Edit** - Manually merge multiple controls at once
- **Merge History** - Audit trail of all merge operations

## See Also

- [Merge Enhancement Implementation](../MERGE_ENHANCEMENT_IMPLEMENTATION.md)
- [Control Merging Workflow](help/workflows/merging.md)
- [Duplicate Highlighting](help/developer/duplicate-highlighting.md)
