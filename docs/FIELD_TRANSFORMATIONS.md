# Field Transformation Documentation

**Last Updated:** 2025-12-16  
**Purpose:** Document all data transformations that occur between extractor output and database storage.

---

## Overview

Some fields undergo transformation between extraction and insertion to maintain consistency with database schema and formatting requirements. This document details each transformation to aid debugging and maintenance.

---

## Control Field Transformations

### 1. Array to Text Conversions

#### control_tests: Array → Text

**Extractor Output:**
```python
"control_tests": [
    "Obtained and inspected...",
    "Performed walkthrough...",
    "Validated configurations..."
]
```

**Transformation:**
```python
# Join array elements with double newlines
control_test = "\n\n".join(control["control_tests"])
```

**Database Value:**
```
Obtained and inspected...

Performed walkthrough...

Validated configurations...
```

**Why:** Database schema uses `text` field, not JSON array. Double newlines preserve readability when displaying in frontend.

**Location:** `backend/app/extractors/control_extractor_unified.py` (merge function)

---

#### control_test_results: Array → Text

**Extractor Output:**
```python
"control_test_results": [
    "No exceptions noted",
    "1 deviation identified",
    "Results satisfactory"
]
```

**Transformation:**
```python
# Join array elements with double newlines
control_test_results = "\n\n".join(control["control_test_results"])
```

**Database Value:**
```
No exceptions noted

1 deviation identified

Results satisfactory
```

**Why:** Same as control_tests - maintains text field compatibility.

**Location:** `backend/app/extractors/control_extractor_unified.py` (merge function)

---

### 2. Confidence Score Aggregation

#### Multi-Factor Confidence → final_confidence

**Extractor Output:**
```python
"verification_metadata": {
    "factor_scores": {
        "gpt_confidence": 0.85,
        "pattern_confidence": 0.72,
        "structure_score": 0.90,
        "framework_score": 0.88,
        "deviation_score": 1.0
    },
    "final_confidence": 0.87
}
```

**Transformation:**
```python
# Weighted average (from control_extractor_combined.py)
weights = {
    "gpt_weight": 0.25,
    "pattern_weight": 0.20,
    "structure_weight": 0.20,
    "framework_weight": 0.20,
    "deviation_weight": 0.15
}

final_confidence = (
    weights["gpt_weight"] * gpt_confidence +
    weights["pattern_weight"] * pattern_confidence +
    weights["structure_weight"] * structure_score +
    weights["framework_weight"] * framework_score +
    weights["deviation_weight"] * deviation_score
)
```

**Database Storage:**
- `final_confidence` (float): Stored as top-level field
- Full breakdown in `verification_metadata` (JSON)

**Why:** Provides single confidence metric while preserving detailed breakdown for analysis.

**Location:** `backend/app/extractors/control_extractor_combined.py` (calculate_5_factor_confidence function)

---

### 3. Framework Selection

#### framework_mappings → primary_framework/criterion/confidence

**Extractor Output:**
```python
"framework_mappings": {
    "TSC": [
        {"criterion_id": "CC1.2", "confidence": 0.92, ...},
        {"criterion_id": "CC6.1", "confidence": 0.78, ...}
    ],
    "COSO": [
        {"criterion_id": "Control Environment", "confidence": 0.65, ...}
    ]
}
```

**Transformation:**
```python
# Find highest confidence mapping across all frameworks
all_mappings = []
for framework, mappings in framework_mappings.items():
    for mapping in mappings:
        all_mappings.append({
            "framework": framework,
            "criterion_id": mapping["criterion_id"],
            "confidence": mapping["confidence"]
        })

best_match = max(all_mappings, key=lambda x: x["confidence"])

primary_framework = best_match["framework"]  # "TSC"
primary_criterion_id = best_match["criterion_id"]  # "CC1.2"
primary_confidence = best_match["confidence"]  # 0.92
```

**Database Storage:**
- `framework_mappings` (JSON): Complete mapping data
- `primary_framework` (varchar): Quick access to best match
- `primary_criterion_id` (varchar): Quick access to best criterion
- `primary_confidence` (float): Quick access to confidence

**Why:** Allows efficient querying by primary framework without parsing JSON.

**Location:** Framework mapping service

---

## CUEC Field Transformations

### confidence_justification: Array → Text

**Extractor Output:**
```python
"confidence_justification": [
    "+0.3: Contains 'user entity' keyword",
    "+0.2: Near CUEC section header",
    "-0.1: Missing responsibility keywords"
]
```

**Transformation:**
```python
# Join array elements with newlines
confidence_justification = "\n".join(cuec["confidence_justification"])
```

**Database Value:**
```
+0.3: Contains 'user entity' keyword
+0.2: Near CUEC section header
-0.1: Missing responsibility keywords
```

**Why:** Preserves itemized justification for display while using text field.

**Location:** `backend/app/extractors/cuec_extractor.py`

---

## Subservice Organization Field Transformations

### confidence_justification: Array → Text

**Extractor Output:**
```python
"confidence_justification": [
    "+0.2: Common provider (AWS)",
    "+0.15: Listed in common_subservice_orgs.txt",
    "+0.1: Near subservice org keywords"
]
```

**Transformation:**
```python
# Join array elements with newlines
confidence_justification = "\n".join(entry["confidence_justification"])
```

**Database Value:**
```
+0.2: Common provider (AWS)
+0.15: Listed in common_subservice_orgs.txt
+0.1: Near subservice org keywords
```

**Why:** Makes confidence calculation transparent while using text field.

**Location:** `backend/app/extractors/subservice_orgs.py` (calculate_confidence function)

---

## Page Reference Transformations

### Control/CUEC: Integer Array → JSON

**Extractor Output:**
```python
"control_page_refs": [15, 16, 23, 24]
```

**Transformation:**
```python
# Store as-is, PostgreSQL JSON handles arrays natively
control_page_refs = [15, 16, 23, 24]
```

**Database Storage:** JSON array `[15, 16, 23, 24]`

**Frontend Display:**
```typescript
// Extract and format for display
const pageRefs = control.control_page_refs.join(", ")  // "15, 16, 23, 24"
```

**Why:** Arrays in JSON preserve structure and allow efficient queries.

**Location:** No transformation needed - stored directly as JSON

---

## Scan ID Injection

### All Extractors: scan_id Addition

**Extractor Output:**
```python
# Extractor may or may not include scan_id
{
    "control_id": "CTL-001",
    ...
}
```

**Transformation:**
```python
# Inject scan_id before insertion
for record in extracted_data:
    record["scan_id"] = current_scan_id
```

**Why:** Ensures all records link to correct scan without extractor needing awareness of scan context.

**Location:** `backend/app/analyze.py` (before INSERT operations)

---

## Null/Empty Value Handling

### Empty String → NULL

**Transformation:**
```python
# Convert empty strings to None (NULL in database)
def clean_empty_values(record):
    for key, value in record.items():
        if isinstance(value, str) and value.strip() == "":
            record[key] = None
    return record
```

**Why:** Database NULL is more semantically correct than empty string for "no value".

**Location:** `backend/app/explicit_sql_insert.py` (before INSERT)

---

### Empty Array → NULL or Empty JSON Array

**Transformation:**
```python
# For optional arrays, convert [] to None
if not control.get("financial_assertions"):
    control["financial_assertions"] = None

# For required arrays, keep []
control["control_page_refs"] = control.get("control_page_refs", [])
```

**Why:** Some arrays are optional (financial_assertions for SOC 2), others are required but may be empty.

**Location:** Extractor post-processing

---

## Boolean Normalization

### String/Various → Boolean

**Transformation:**
```python
# Normalize truthy values to Python bool
def normalize_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1', 't', 'y')
    return bool(value)

has_deviation = normalize_boolean(control.get("has_deviation", False))
```

**Why:** Extractors may return various truthy representations; normalize for database consistency.

**Location:** Data validation layer before INSERT

---

## Timestamp Handling

### ISO String → DateTime

**Transformation:**
```python
from datetime import datetime

# Parse ISO format string to datetime object
if isinstance(value, str):
    timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
else:
    timestamp = value
```

**Why:** SQLAlchemy expects datetime objects, not ISO strings.

**Location:** `backend/app/models.py` (Column definitions handle this automatically)

---

## JSON Structure Validation

### Nested Objects: Validation & Defaults

**Transformation:**
```python
# Ensure framework_mappings has expected structure
if not isinstance(control.get("framework_mappings"), dict):
    control["framework_mappings"] = {}

# Ensure each framework has array of mappings
for framework in ["TSC", "COSO", "FINANCIAL_ASSERTIONS"]:
    if framework not in control["framework_mappings"]:
        control["framework_mappings"][framework] = []
    elif not isinstance(control["framework_mappings"][framework], list):
        control["framework_mappings"][framework] = []
```

**Why:** Prevents JSON structure errors and ensures consistent querying.

**Location:** Post-extraction validation

---

## Summary of Critical Transformations

| Field | From | To | Reason |
|-------|------|-----|--------|
| `control_tests` | `[str]` | `text` | Database schema uses text, not array |
| `control_test_results` | `[str]` | `text` | Database schema uses text, not array |
| `final_confidence` | 5 factors | `float` | Weighted average of all factors |
| `primary_framework` | JSON mappings | `varchar` | Extract best match for efficient querying |
| `confidence_justification` | `[str]` | `text` | Preserve itemization in text field |
| Empty strings | `""` | `NULL` | NULL is more semantically correct |
| `scan_id` | N/A | `int` | Injected by pipeline, not extractor |

---

## Debugging Tips

### When INSERT Fails

1. **Check transformation logs:** Transformations are logged with `[TRANSFORM]` prefix
2. **Validate types:** Use `type()` to verify field types match expected
3. **Check for None:** Ensure required fields aren't None/NULL
4. **Validate JSON structure:** Use `json.loads()` to verify JSON fields are valid

### When Data Looks Wrong

1. **Check transformation order:** Some fields depend on others being transformed first
2. **Check for overwrites:** Later transformations may overwrite earlier values
3. **Verify extractor output:** Log raw extractor output before transformation
4. **Compare with schema:** Reference EXTRACTOR_OUTPUT_SCHEMAS.md

---

## Future Improvements

1. **Centralize transformations:** Consider single transformation module instead of scattered locations
2. **Add transformation tests:** Unit tests for each transformation function
3. **Document transformation order:** Create dependency graph of transformations
4. **Add transformation metrics:** Track transformation failures and performance

---

**END OF FIELD TRANSFORMATIONS**
