# Incremental Write Implementation Plan

## Problem Statement
Current architecture holds all controls in memory during extraction (~40+ minutes) with no visibility, no checkpointing, and risk of data loss on crash. Framework mapping taking 162+ controls × 14 seconds = 38+ minutes with zero partial results.

## Current Flow
```
Extract controls → Hold in memory → Map frameworks (batch) → Write to disk (once)
                   ^                ^                        ^
                   |                |                        |
                   No visibility    No visibility            Single point of failure
```

## Proposed Architecture

### Phase 1: Incremental Control Writing (High Priority)
**Goal**: Write controls as extracted, maintain visibility, enable resume capability

#### Changes to `backend/app/extractors/control_extractor.py`

1. **Add checkpoint file path** (around line 50-60 in imports/config section):
```python
CHECKPOINT_FILE = config.CONTROL_JSON_PATH.replace('.json', '_checkpoint.json')
```

2. **Add incremental write function** (around line 900, before framework mapping):
```python
def write_checkpoint(validated_controls, rejected_controls, diagnostics, scan_id=None):
    """Write current extraction state to checkpoint file"""
    checkpoint_data = {
        "scan_id": scan_id,
        "timestamp": datetime.now().isoformat(),
        "status": "in_progress",
        "controls": validated_controls,
        "rejected_controls": rejected_controls,
        "diagnostics": diagnostics,
        "control_count": len(validated_controls)
    }
    
    checkpoint_path = CHECKPOINT_FILE
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Checkpoint saved: {len(validated_controls)} controls")
```

3. **Add checkpoint calls in main extraction loop** (around line 800-850, after each chunk):
```python
# After validating controls in each chunk (find the section with validated_controls.append())
validated_controls.append(control_dict)
logger.info(f"✓ Control {control_id} validated and added")

# Add checkpoint every 10 controls
if len(validated_controls) % 10 == 0:
    write_checkpoint(validated_controls, rejected_controls, diagnostics, scan_id=scan_id)
```

4. **Keep framework mapping as separate post-processing** (no changes to lines 945-995):
   - Framework mapping stays as batch operation after extraction completes
   - Applied to all controls at once (current logic preserved)

5. **Final write includes framework mappings** (around line 1062, existing logic):
```python
# Existing code - just document that this is the final write
# Checkpoint file becomes the final result file when framework mapping completes
output = {
    "controls": validated_controls,  # Now includes framework_mappings
    "diagnostics": diagnostics,
    "rejected_controls": rejected_controls
}

with open(config.CONTROL_JSON_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

# Clean up checkpoint file
if os.path.exists(CHECKPOINT_FILE):
    os.remove(CHECKPOINT_FILE)
```

### Phase 2: Resume Capability (Medium Priority)
**Goal**: Resume interrupted extractions

#### Add resume logic at start of `extract_controls_unified()`:
```python
def extract_controls_unified(
    pdf_path: str,
    report_type: str = "SOC2",
    scan_id: Optional[str] = None,
    max_controls: Optional[int] = None,
    resume: bool = False  # New parameter
):
    # Check for existing checkpoint
    if resume and os.path.exists(CHECKPOINT_FILE):
        logger.info("Found checkpoint file - loading previous progress")
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)
        
        if checkpoint.get('status') == 'in_progress':
            validated_controls = checkpoint.get('controls', [])
            rejected_controls = checkpoint.get('rejected_controls', [])
            diagnostics = checkpoint.get('diagnostics', {})
            
            logger.info(f"Resuming from checkpoint: {len(validated_controls)} controls already extracted")
            
            # TODO: Implement smart resume (skip already-extracted page ranges)
            # For now, just log that we found previous work
            # Full implementation would track which pages were processed
```

### Phase 3: API Enhancement (Low Priority)
**Goal**: Support `max_controls` for quick testing

#### Changes to `backend/app/analyze.py` (lines 360-363):
```python
# Add max_controls parameter to endpoint
@router.post("/analyze/")
async def analyze_endpoint(
    # ... existing parameters ...
    max_controls: Optional[int] = None  # Add this
):
    # Pass to extractor
    controls = await extract_controls_unified(
        pdf_path=pdf_path,
        report_type=report_type,
        scan_id=job_id,
        max_controls=max_controls  # Pass through
    )
```

#### Update `control_extractor.py` extraction loop to respect max_controls:
```python
# In main extraction loop (around line 800)
if max_controls and len(validated_controls) >= max_controls:
    logger.info(f"Reached max_controls limit: {max_controls}")
    break
```

## Benefits

### Immediate
- ✅ **Visibility**: See controls as they're extracted via checkpoint file
- ✅ **Safety**: If crash occurs, controls already saved
- ✅ **Monitoring**: Track progress in real-time
- ✅ **Memory**: Reduced memory footprint (though minimal impact with 200 controls)

### Future
- ✅ **Resume**: Continue interrupted scans
- ✅ **Quick Testing**: Test with 10 controls instead of full scan
- ✅ **Debugging**: Inspect partial results to debug extraction issues
- ✅ **User Experience**: Progress bar reflects actual control count

## Implementation Order

1. **Tonight/Tomorrow Morning** (30 minutes):
   - Add `write_checkpoint()` function
   - Add checkpoint calls every 10 controls
   - Test with Okta.pdf to verify checkpoints appear

2. **After Validation** (15 minutes):
   - Add checkpoint cleanup on successful completion
   - Verify framework mapping still works correctly

3. **Phase 2 - Resume** (1-2 hours):
   - Add `--resume` flag support
   - Implement page tracking for smart resume
   - Test interrupt/resume cycle

4. **Phase 3 - API max_controls** (30 minutes):
   - Add parameter to API endpoint
   - Update extractor to respect limit
   - Test 10-control quick scan

## Testing Plan

### Test 1: Checkpoint Creation
```bash
# Start scan, interrupt after 30 seconds
# Check: c:\Users\bklumpp\...\data\json\control_result_checkpoint.json exists
# Verify: Contains controls extracted so far
```

### Test 2: Full Completion
```bash
# Let scan complete fully
# Check: Framework mappings applied to all controls
# Check: Checkpoint file removed
# Verify: control_result.json has all controls with framework_mappings
```

### Test 3: Resume (Phase 2)
```bash
# Start scan, interrupt after 50 controls
# Restart with --resume flag
# Verify: Continues from checkpoint (doesn't re-extract)
```

### Test 4: Max Controls (Phase 3)
```bash
# Run with max_controls=10
# Verify: Stops after 10 controls
# Verify: Completes in 5-10 minutes instead of 40+
```

## Risks & Mitigation

**Risk**: Framework mapping fails with incremental writes
- **Mitigation**: Framework mapping still runs as batch after extraction (no change to that logic)

**Risk**: Checkpoint file becomes corrupted
- **Mitigation**: Use atomic writes (write to temp file, then rename)

**Risk**: Resume skips controls
- **Mitigation**: Phase 2 implementation tracks page ranges explicitly

## Files to Modify

1. **backend/app/extractors/control_extractor.py** (Primary changes)
   - Lines 50-60: Add CHECKPOINT_FILE constant
   - Lines 900-920: Add write_checkpoint() function
   - Lines 800-850: Add checkpoint calls in extraction loop
   - Lines 1062-1070: Add checkpoint cleanup

2. **backend/app/analyze.py** (Phase 3)
   - Lines 360-363: Add max_controls parameter

3. **backend/app/config.py** (Optional)
   - Add CHECKPOINT_ENABLED flag for feature toggle

## Success Criteria

- ✅ Checkpoint file appears within 2 minutes of scan start
- ✅ Checkpoint updates every ~10 controls
- ✅ Can inspect partial results during active scan
- ✅ Framework mapping completes successfully
- ✅ Final JSON identical to current architecture (with frameworks)
- ✅ No performance degradation (I/O is minimal)

## Next Steps

**Tomorrow morning**:
1. Check if overnight scan completed
2. If yes: Validate framework mappings worked correctly
3. If no: Cancel scan and implement Phase 1
4. Test Phase 1 with Okta.pdf (should see checkpoints)
5. If successful, commit and move to Phase 2

**Command to check scan status tomorrow**:
```powershell
docker logs socanalyzer-backend --tail 50 | Select-String -Pattern "Saved.*controls|complete|error"
```
