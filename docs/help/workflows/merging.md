# Control Merging Workflow

## Overview

The control merging system automatically detects and consolidates duplicate controls extracted from SOC reports. This reduces manual review burden and ensures data quality.

## How It Works

### 1. Automated Detection

After extraction completes, the system runs `automated_cleanup()`:

```
For each control_id:
  ├─ Find all controls with same ID
  ├─ Sort by confidence (highest first)
  ├─ Select primary (highest confidence)
  └─ Compare each duplicate to primary
      ├─ Calculate similarity score (0.0-1.0)
      ├─ If score ≥ 0.70: Auto-merge
      ├─ If score < 0.60: Flag as extraction error
      └─ Otherwise: Add to manual review queue
```

### 2. Similarity Scoring

The system uses a multi-factor confidence score:

| Factor | Weight | Description |
|--------|--------|-------------|
| Description Similarity | 65% | GPT-based semantic comparison |
| TSC/COSO Match | 15% | Framework alignment agreement |
| Test Procedure | 10% | Test description similarity |
| Deviation Agreement | 5% | Same deviation status |
| **Page Proximity** | **+5%** | **Adjacent pages bonus** |

**Total possible score: 1.00** (100%)

### 3. Auto-Merge Threshold

Controls with similarity ≥ **0.70** (70%) are automatically merged:

```python
if confidence_score >= 0.70:
    # Merge candidate into primary
    candidate.merged_to_control_id = primary.id
    candidate.control_confidence = 0.0
    
    # Track merge history
    primary.merge_history.append({
        "timestamp": "2025-12-03T12:34:56",
        "type": "auto",
        "confidence": 0.75,
        "merged_from_ids": ["456"],
        "reason": "Automated cleanup"
    })
```

## Page Proximity Detection

### Problem: Chunk-Split Duplicates

Large controls spanning multiple pages may be split across PDF processing chunks, creating apparent duplicates:

```
Page 45: Control IAM-01 (partial)
  ↓ Chunk boundary
Page 46: Control IAM-01 (continuation)
```

### Solution: Adjacent Page Bonus

If controls are on adjacent pages, add +5% to similarity score:

```python
if abs(primary_max_page - candidate_min_page) <= 1:
    confidence_score += 0.05  # +5% bonus
```

This helps catch duplicates that might otherwise score 68% (below threshold) but are clearly the same control split across pages.

## Manual Merge Review

### Viewing Suggestions

1. Go to **Controls Tab**
2. Click **"Suggest Merges"** button
3. Review list of potential duplicates

Each suggestion shows:
- Control ID and descriptions
- Confidence score with breakdown
- Page references
- Primary control selection

### Approving Merges

Click **"Merge"** on a suggestion to:
1. Consolidate all data into primary control
2. Set secondary controls to confidence = 0
3. Mark secondaries as merged (`merged_to_control_id`)
4. Add entry to `merge_history`

### Intelligent Primary Selection

System selects primary control based on:

1. **Longest description** (most complete)
2. **Highest confidence** (if descriptions equal)
3. **Lowest ID** (first extracted, if tied)

## Merge History Tracking

Every merge creates an audit trail entry:

```json
{
  "timestamp": "2025-12-03T12:34:56.789",
  "type": "auto",
  "confidence": 0.753,
  "merged_from_ids": ["456", "789"],
  "reason": "Automated cleanup: duplicate control_id with 0.75 similarity"
}
```

**Type values:**
- `"auto"`: Automatic merge during cleanup
- `"manual"`: User-initiated merge via UI

**Access merge history:**
```sql
SELECT id, control_id, merge_history 
FROM control 
WHERE merge_history IS NOT NULL;
```

## Quality Checks

### Incomplete Control Penalty

Controls missing required fields are penalized -20% confidence:

**Required fields:**
- control_id
- control_desc
- control_test
- control_test_results

```python
if any_field_missing:
    control.control_confidence -= 0.20
```

### Extraction Error Flagging

Controls with very low similarity (<60%) to duplicates are flagged:

```python
if confidence_score < 0.60:
    control.control_confidence = 0.30
    control.confidence_calc += "\nLikely extraction error"
```

## Configuration

### Environment Variables

```bash
# Minimum score for auto-merge (default: 0.70)
AUTO_MERGE_MIN_CONFIDENCE=0.70

# Bonus for adjacent pages (default: 0.05)
PAGE_PROXIMITY_WEIGHT=0.05

# Penalty for incomplete controls (default: 0.20)
CONTROL_INCOMPLETE_PENALTY=0.20

# Minimum score for manual suggestions (default: 0.50)
MERGE_SUGGESTION_MIN_CONFIDENCE=0.50
```

### Adjusting Thresholds

**More aggressive merging:**
```bash
AUTO_MERGE_MIN_CONFIDENCE=0.65  # Lower threshold
```

**More conservative merging:**
```bash
AUTO_MERGE_MIN_CONFIDENCE=0.80  # Higher threshold
```

## Best Practices

### When to Merge Manually

✅ **Good candidates for merging:**
- Score ≥ 0.60 but < 0.70
- Same control_id and similar descriptions
- Adjacent pages
- Same TSC/COSO mapping

❌ **Do NOT merge:**
- Different descriptions (< 0.50 similarity)
- Different deviation status without review
- Unclear which is correct version

### Reviewing Auto-Merges

Periodically check auto-merged controls:

```sql
SELECT * FROM control 
WHERE merge_history IS NOT NULL 
AND merge_history::text LIKE '%"type": "auto"%';
```

Look for:
- Unexpectedly high merge counts
- Low confidence auto-merges (0.70-0.75 range)
- Important controls that were merged

### Undoing Merges

To unmerge a control:

1. Find merged control (merged_to_control_id IS NOT NULL)
2. Set merged_to_control_id = NULL
3. Restore original confidence from annotation
4. Remove primary control's merge_history entry

## Troubleshooting

### Too Many Duplicates Remaining

**Possible causes:**
- Threshold too high (0.70)
- Poor PDF text extraction
- Non-standard control formatting

**Solutions:**
- Lower AUTO_MERGE_MIN_CONFIDENCE to 0.65
- Review and manually approve suggestions
- Check PDF quality

### False Positive Merges

**Possible causes:**
- Threshold too low
- Similar but distinct controls

**Solutions:**
- Raise AUTO_MERGE_MIN_CONFIDENCE to 0.75
- Review merge_history for patterns
- Unmerge incorrect merges

### Page Proximity Not Working

**Possible causes:**
- Page references not extracted
- Non-numeric page references

**Check:**
```sql
SELECT id, control_id, control_page_refs 
FROM control 
WHERE control_page_refs IS NULL 
OR jsonb_array_length(control_page_refs) = 0;
```

## See Also

- [Extraction Workflow](#extraction-workflow) - How controls are extracted
- [Controls Tab](#controls-tab) - Managing control data
- [Database Schema](#database) - merge_history column structure
