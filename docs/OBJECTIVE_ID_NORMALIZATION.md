# Objective ID Normalization Implementation

## Overview
This document describes the objective ID normalization system implemented to ensure consistent storage, display, sorting, and searching of control objective identifiers across different report formats.

## Problem Statement
SOC reports use varying objective ID formats:
- `CC 6.1` (with spaces)
- `CC6.1` (without spaces)  
- `CC 6.1 - Additional Context` (with suffix)
- `CC-6.1` (different separator)

This inconsistency caused:
1. **Matching failures** during gap extraction (searching for "CC6.1" couldn't find "CC 6.1")
2. **Inconsistent sorting** (lexical sort of mixed formats produces incorrect order)
3. **Display inconsistencies** (same objective shown differently across UI)
4. **PDF search failures** (normalized ID won't match original PDF text)

## Solution Architecture

### Three-Field Strategy
The solution stores objective IDs in three ways:

1. **`objective_id`** (DEPRECATED): Legacy field, kept for backwards compatibility
2. **`objective_id_normalized`** (PRIMARY): Normalized format for display/sorting/comparison
   - Removes spaces before dots and dashes: `"CC 6.1"` → `"CC6.1"`
   - Collapses multiple spaces to single space
   - Used for UI display, sorting, and matching logic
   
3. **`objective_id_original`** (SEARCH): Original PDF format for searching
   - Preserves exact format from PDF extraction
   - Used when searching/highlighting text in PDF viewer
   - Ensures accurate text location even with format variations

### Pattern Translator
The `Scan.pattern_info` field stores GPT-extracted objective ID patterns as JSON:
```json
{
  "common_controls": {
    "pattern": "CC X.Y",
    "examples": ["CC 6.1", "CC 6.2", "CC 6.3"]
  },
  "additional_criteria": {
    "pattern": "A X",
    "examples": ["A 1", "A 2"]
  }
}
```

This enables:
- **Format detection**: Identify which pattern group an objective belongs to
- **Denormalization**: Convert normalized IDs back to original format when needed
- **Format consistency**: Apply same format to gap-extracted objectives

## Database Schema

### Migration: `53c002f21ab0_add_objective_id_normalization_fields.py`

Added fields:
- `scan.pattern_info` (JSONB): Stores objective ID patterns
- `control_objectives.objective_id_normalized` (String, indexed): Normalized ID
- `control_objectives.objective_id_original` (String): Original PDF format

The migration includes backfill logic that:
1. Copies existing `objective_id` to both new fields
2. Applies normalization regex to `objective_id_normalized`
3. Creates index for efficient sorting/searching

## Backend Implementation

### Normalization Utility: `backend/app/utils/objective_id_normalizer.py`

Key functions:
```python
def normalize_objective_id(objective_id: str) -> str:
    """Remove spaces before dots/dashes, collapse multiple spaces"""
    if not objective_id:
        return ""
    # "CC 6.1" → "CC6.1"
    normalized = re.sub(r'\s+([.-])', r'\1', objective_id.strip())
    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized

def denormalize_objective_id(
    normalized_id: str, 
    pattern_info: dict, 
    fallback: str = None
) -> str:
    """Convert normalized ID back to original format using pattern_info"""
    # Uses pattern_info to determine format (e.g., add space before dot)
    ...

def get_pattern_for_objective(objective_id: str, pattern_info: dict) -> dict:
    """Find which pattern group an objective belongs to"""
    ...
```

### Integration Points

#### 1. Objective Extraction (`objective_extractor.py`)
When extracting objectives from SOC reports:
```python
original_objective_id = obj.get('objective_id')
normalized_objective_id = normalize_objective_id(original_objective_id)

new_obj = ControlObjective(
    objective_id=original_objective_id,  # DEPRECATED field
    objective_id_normalized=normalized_objective_id,  # For display/sorting
    objective_id_original=original_objective_id,  # For PDF search
    ...
)
```

#### 2. Gap Extraction (`objective_router.py`)
When storing GPT-extracted patterns:
```python
# After GPT extracts objective ID patterns
scan_row = db.execute(select(Scan).where(Scan.id == scan_id)).scalar_one()
scan_row.pattern_info = pattern_data  # Store patterns
db.commit()
```

When creating objectives from gap search:
```python
def _create_objective_from_extraction(search_id: str, extracted: dict):
    objective_id = extracted.get("objective_id")
    original_objective_id = objective_id
    normalized_objective_id = normalize_objective_id(objective_id)
    
    new_obj = ControlObjective(
        objective_id=objective_id,
        objective_id_normalized=normalized_objective_id,
        objective_id_original=original_objective_id,
        ...
    )
```

## Frontend Implementation

### Type Definition (`objectiveService.ts`)
```typescript
export interface ControlObjective {
  objective_id: string | null;  // DEPRECATED
  objective_id_normalized: string | null;  // Use for display
  objective_id_original: string | null;  // Use for PDF search
  ...
}
```

### Display Updates
All UI components updated to use normalized ID:

1. **ObjectivesModal.tsx**: Main objectives table
   ```tsx
   <TableCell>{obj.objective_id_normalized || obj.objective_id || '—'}</TableCell>
   ```

2. **ObjectiveSelector.tsx**: Control mapping selector
   ```tsx
   {mapping.objective.objective_id_normalized || mapping.objective.objective_id}
   ```

3. **ObjectivesCoverageTab.tsx**: Coverage report display
   ```tsx
   {objective.objective_id_normalized || objective.objective_id}
   ```

The fallback to `objective_id` ensures compatibility with old data.

## Usage Guidelines

### For Display/Sorting
Always use `objective_id_normalized`:
```python
# Sort objectives
objectives.sort(key=lambda o: o.objective_id_normalized or "")

# Display in UI
display_text = objective.objective_id_normalized or "N/A"
```

### For PDF Searching
Always use `objective_id_original`:
```python
# Search PDF for objective
search_term = objective.objective_id_original
pdf_search(search_term)
```

### For Matching/Comparison
Normalize both sides:
```python
# Check if objective exists
existing = db.query(ControlObjective).filter(
    func.lower(ControlObjective.objective_id_normalized) == 
    normalize_objective_id(search_id).lower()
).first()
```

## Benefits

1. **Consistent Display**: All objectives shown in same format across UI
2. **Reliable Sorting**: Normalized IDs sort correctly (CC6.1 before CC6.10)
3. **Accurate Matching**: Gap extraction finds objectives regardless of format
4. **PDF Search Compatibility**: Original format preserved for text searching
5. **Future-Proof**: Pattern translator supports format conversion

## Testing

To verify the implementation:

1. **Extract objectives** from a SOC report with varied formats
2. **Check database**: Verify all three ID fields are populated
3. **Run gap extraction**: Confirm it finds objectives regardless of format
4. **View in UI**: Verify consistent display format
5. **Search PDF**: Confirm original format is used for searching

## Migration Steps

To apply this to an existing deployment:

1. Run migration: `alembic upgrade head`
2. Restart backend services
3. Rebuild frontend: `npm run build`
4. Deploy updated code

Existing data will be automatically backfilled with normalized values.

## Future Enhancements

Potential improvements:
1. **Auto-format detection**: Automatically detect most common format per scan
2. **User preferences**: Allow users to choose display format
3. **Pattern validation**: Warn when objective doesn't match known patterns
4. **Batch normalization**: Admin tool to re-normalize existing objectives
