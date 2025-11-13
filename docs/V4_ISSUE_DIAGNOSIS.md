# V4 Multi-Control Extraction - Issue Diagnosis

## Problem
After implementing multi-control extraction, the last scan produced `control_result.json` with just `{}` (empty dict) instead of proper extraction results.

## Timeline
- **11:24 AM**: Test run with old single-control code → 30 controls extracted successfully
- **1:55 PM**: Scan with new multi-control code → 0 controls (`{}` written to file)

## Root Cause Analysis

The empty `{}` file suggests one of the following:

1. **Early Exception**: Extraction crashed before reaching the save point
2. **Initialization Issue**: File was initialized with `{}` and never updated
3. **Return Type Mismatch**: Functions returning `None` when list expected
4. **List Extension Error**: `raw_controls.extend(None)` causing crash

## Code Changes That May Have Broken Things

### Change 1: `parse_control_json()` returns `List[Dict]`
**Risk**: If GPT returns old format and parsing fails in fallback, returns `None` instead of empty list

### Change 2: `extract_control_with_cot()` returns `List[Dict]`
**Risk**: If it returns `None`, then `raw_controls.extend(None)` will crash

### Change 3: Loop uses `extend()` instead of `append()`
```python
controls_from_chunk = extract_control_with_cot(chunk)
if controls_from_chunk:
    raw_controls.extend(controls_from_chunk)
```
**Risk**: If `controls_from_chunk` is `None`, the `if` check prevents crash, but if it's somehow not None but also not a list, `extend()` will fail

## Most Likely Issue

Looking at the code, if `extract_control_with_cot()` returns `None` for all chunks (which could happen if GPT is returning a format the parser doesn't recognize), then:
- `raw_controls` = `[]` (empty list)
- `merged_controls` = `[]`
- `validated_controls` = `[]`
- `diagnostics` is created successfully
- File should be written as:
  ```json
  {
    "controls": [],
    "diagnostics": {actual diagnostics}
  }
  ```

But the file is just `{}`, which means **the extraction never reached the save point**.

## Hypothesis

**GPT is now returning the new format** `{"controls": [...]}` but there's an edge case in the parsing that's causing an exception, and a global exception handler is catching it and writing `{}`.

OR

**The extraction is working but crashing during post-processing** (merge/filter/validate) due to unexpected data structure.

## Solution

Need to add better error handling and logging to identify where exactly the crash is occurring. The function should write partial results even if it crashes partway through.

## Immediate Actions

1. Add try-catch around the entire extraction with explicit error logging
2. Make parse functions return empty list `[]` instead of `None` on failure
3. Add validation that `controls_from_chunk` is actually a list before extending
4. Test with a single chunk to isolate the issue
