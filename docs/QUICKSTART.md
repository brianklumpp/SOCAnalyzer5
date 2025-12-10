# Quick Start Guide - SOC Analyzer Enhancements

## Prerequisites
- Python 3.9+ with all dependencies installed
- Node.js 16+ for frontend
- PostgreSQL database running
- Redis server (for framework preview rate limiting)

## Step 1: Database Migration

```powershell
cd backend
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade -> 20251119_multi_page_refs, multi page refs
```

**Verify migration:**
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'control' AND column_name = 'control_page_refs';
```
Should return: `control_page_refs | json`

---

## Step 2: Configure Environment Variables

Add to your `.env` file or environment:

```bash
# TSC Anomaly Detection (adaptive threshold)
TSC_ANOMALY_BASE_THRESHOLD=20
TSC_ANOMALY_ADAPTIVE_ENABLED=true
TSC_ANOMALY_MIN_THRESHOLD=5

# Merge Suggestions (intelligent duplicate detection)
MERGE_SUGGESTION_MIN_CONFIDENCE=0.85
MERGE_SUGGESTION_MAX_RESULTS=50

# Framework Preview (rate limiting)
FRAMEWORK_PREVIEW_RATE_LIMIT=10
```

---

## Step 3: Start Redis (for Framework Preview)

### Option A: Docker
```powershell
docker run -d --name redis-socanalyzer -p 6379:6379 redis:latest
```

### Option B: Windows Native
Download and install: https://github.com/microsoftarchive/redis/releases

**Verify Redis:**
```powershell
redis-cli ping
# Expected: PONG
```

---

## Step 4: Restart Backend

```powershell
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Test new endpoints:**
```powershell
# Test merge suggestions
curl http://localhost:8000/report/1/controls/suggest-merges

# Test framework preview
curl -X POST http://localhost:8000/report/1/preview-frameworks `
  -H "Content-Type: application/json" `
  -d '{"control_desc":"Management reviews user access quarterly"}'
```

---

## Step 5: Rebuild Frontend

```powershell
cd frontend
npm install  # Install any new dependencies
npm run build
```

**For development:**
```powershell
npm start
```

---

## Step 6: Verify Features

### ✅ Multi-Page References
1. Upload a SOC2 report
2. Go to Controls table
3. Look for "Page Refs" column
4. Should show comma-separated values: `51, 52, 89`

### ✅ Merge Suggestions
1. Open report with duplicate control IDs
2. Look for orange chip badge: "5 suggested merges"
3. Click badge to open drawer
4. Verify confidence scores (70% desc + 15% framework + 10% test + 5% deviation)

### ✅ Merge Operations
1. In merge drawer, click "Merge" on a suggestion
2. Verify primary control shows consolidated page refs
3. Check merged control has `merged_to_control_id` set
4. Test "Split" to undo merge

### ✅ Framework Preview
1. Click "Add Control" button
2. Switch to "Preview Mappings" tab
3. Enter description in Manual Entry tab
4. Switch back to Preview Mappings
5. Click "Compute Preview"
6. Verify TSC/COSO matches display within 3-5 seconds

### ✅ Enhanced Tooltips
1. Find control with multiple TSC mappings
2. Hover over info icon (ℹ️)
3. Wait 500ms for tooltip to appear
4. Verify shows top 3 matches with confidence %, reasoning
5. Check for "+N more" text if >3 matches

### ✅ Adaptive TSC Anomaly
1. Upload large report (200+ controls)
2. Check backend logs for:
   ```
   [TSC ANOMALY] Threshold: 23 (adaptive=on, base=20, 10%=23, total_controls=230)
   ```
3. Verify controls with CC6.1-type anomalies have reduced confidence

---

## Common Issues & Solutions

### Issue 1: Migration Fails
**Error:** `relation "control" does not exist`

**Solution:**
```powershell
# Check current revision
alembic current

# If behind, upgrade
alembic upgrade head
```

### Issue 2: Redis Connection Failed
**Error:** `Failed to connect to Redis`

**Solution:**
- Framework preview will still work (no rate limiting)
- Check Redis is running: `redis-cli ping`
- Verify port 6379 is not blocked by firewall

### Issue 3: Merge Suggestions Empty
**Possible Causes:**
- No duplicate control IDs in report
- All duplicates below 0.85 confidence threshold

**Debug:**
```python
# Check for duplicate control_ids
SELECT control_id, COUNT(*) 
FROM control 
WHERE scan_id = 1 
GROUP BY control_id 
HAVING COUNT(*) > 1;
```

### Issue 4: Page Refs Not Displaying
**Check:**
1. Column visible in table settings (gear icon)
2. Data migrated: `SELECT control_page_refs FROM control LIMIT 5;`
3. Frontend showing `control_page_refs` not `control_page_ref`

### Issue 5: Tooltip Not Showing
**Verify:**
- Hover for full 500ms (delay intentional)
- `control_tsc_mappings` or `control_coso_mappings` exists in row data
- Check browser console for React errors

---

## Performance Tips

### Backend
- Monitor GPT API costs (merge suggestions call GPT for each pair)
- Consider caching merge suggestions for 5 minutes
- Use `throttle_ms` in batch operations to avoid rate limits

### Frontend
- Enable column hiding for better performance with large datasets
- Use pagination if controls exceed 500 rows
- Clear browser cache if tooltips lag

### Database
- Add index on `control_id` if merge suggestions slow:
  ```sql
  CREATE INDEX idx_control_control_id ON control(control_id);
  ```
- Monitor JSON column size for very large page ref arrays

---

## Rollback Instructions

If critical issues arise:

### 1. Database Rollback (⚠️ LOSES MULTI-PAGE DATA)
```powershell
cd backend
alembic downgrade -1
```

### 2. Code Rollback
```powershell
git log --oneline  # Find commit before changes
git checkout <commit-hash>
```

### 3. Config Rollback
Remove new environment variables or restart with defaults.

---

## Next Steps

After verifying all features work:

1. **Run full extraction pipeline** on test report
2. **Review merge suggestions** for accuracy
3. **Test batch operations** with large datasets
4. **Monitor GPT API usage** for cost implications
5. **Train users** on new merge workflow
6. **Document edge cases** in production use

---

## Support

For issues or questions:
1. Check `backend_recent.log` for API errors
2. Review browser console for frontend issues
3. Verify Redis connection with `redis-cli ping`
4. Check Alembic migration status with `alembic current`

**Logs to monitor:**
- `backend/backend_recent.log` - API requests
- `data/logs/*_extractor.log` - Extraction pipeline
- Browser console - React errors
- Redis logs - Rate limiting issues

---

## Success Criteria

All features working when:
- ✅ Migration applied successfully
- ✅ Page refs show comma-separated values
- ✅ Merge suggestions chip shows non-zero count
- ✅ Merge operations consolidate page refs
- ✅ Split restores original confidence
- ✅ Framework preview completes in <10 seconds
- ✅ Tooltips appear after 500ms hover
- ✅ TSC anomaly reduces confidence in logs
- ✅ No errors in backend logs or browser console

**Total Implementation Time:** Backend (2-3 hours) + Frontend (1-2 hours) + Testing (1 hour)

**Deployment Ready**: After passing all verification steps above ✨
