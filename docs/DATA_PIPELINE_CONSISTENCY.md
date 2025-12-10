# Data Pipeline Consistency Verification

## Overview

This document verifies field name consistency across the entire data pipeline:
**Extraction → JSON → Database**

## Framework Mapping Fields

### Core Multi-Framework Fields

| Field Name | Extractor Output | JSON File | Database Column | Type |
|------------|------------------|-----------|-----------------|------|
| `framework_mappings` | ✅ | ✅ | ✅ | JSONB |
| `primary_framework` | ✅ | ✅ | ✅ | String(64) |
| `primary_criterion_id` | ✅ | ✅ | ✅ | String(128) |
| `primary_confidence` | ✅ | ✅ | ✅ | Float |

### Legacy Multi-Match Arrays (Backward Compatibility)

| Field Name | Extractor Output | JSON File | Database Column | Type |
|------------|------------------|-----------|-----------------|------|
| `control_tsc_mappings` | ✅ | ✅ | ✅ | JSON Array |
| `control_coso_mappings` | ✅ | ✅ | ✅ | JSON Array |
| `cuec_tsc_mappings` | ✅ | ✅ | ✅ | JSON Array |
| `cuec_coso_mappings` | ✅ | ✅ | ✅ | JSON Array |

### Legacy Single-Match Fields (Deprecated but Retained)

| Field Name | Extractor Output | JSON File | Database Column | Type |
|------------|------------------|-----------|-----------------|------|
| `control_tsc_id` | ✅ | ✅ | ✅ | String(128) |
| `control_coso_id` | ✅ | ✅ | ✅ | String(128) |
| `control_closest_framework` | ✅ | ✅ | ✅ | String(128) |
| `cuec_tsc_id` | ✅ | ✅ | ✅ | String(128) |
| `cuec_coso_id` | ✅ | ✅ | ✅ | String(128) |
| `cuec_closest_framework` | ✅ | ✅ | ✅ | String(128) |

### SOC1-Specific Fields

| Field Name | Extractor Output | JSON File | Database Column | Type |
|------------|------------------|-----------|-----------------|------|
| `financial_assertions` | ✅ | ✅ | ✅ | JSON Array |
| `framework_category` | ✅ | ✅ | ✅ | String(32) |

## Data Structure Examples

### Control with Multi-Framework Mappings (JSON)

```json
{
  "control_id": "AC-001",
  "control_desc": "Access reviews performed quarterly",
  "has_deviation": false,
  
  "framework_mappings": {
    "TSC": [
      {
        "id": "CC6.1",
        "confidence": 0.92,
        "keywords_matched": ["access", "review", "quarterly"],
        "aspect_addressed": "Monitoring of access rights",
        "reasoning": "Periodic access review aligns with entity monitoring"
      },
      {
        "id": "CC7.2",
        "confidence": 0.88,
        "keywords_matched": ["access", "authorization"],
        "aspect_addressed": "Access control validation",
        "reasoning": "Reviews validate authorized access"
      }
    ],
    "COSO": [
      {
        "id": "10",
        "confidence": 0.85,
        "keywords_matched": ["access control", "review"],
        "aspect_addressed": "Control Activities - Segregation",
        "reasoning": "Access review is a control activity"
      }
    ]
  },
  
  "primary_framework": "TSC",
  "primary_criterion_id": "CC6.1",
  "primary_confidence": 0.92,
  
  "control_tsc_mappings": [
    {"id": "CC6.1", "confidence": 0.92, "reasoning": "..."},
    {"id": "CC7.2", "confidence": 0.88, "reasoning": "..."}
  ],
  
  "control_coso_mappings": [
    {"id": "10", "confidence": 0.85, "reasoning": "..."}
  ],
  
  "control_tsc_id": "CC6.1",
  "control_coso_id": "10",
  "control_closest_framework": "TSC"
}
```

### SOC1 Control with Financial Assertions (JSON)

```json
{
  "control_id": "REV-005",
  "control_desc": "Revenue transactions are authorized and accurately recorded",
  "has_deviation": false,
  
  "framework_mappings": {
    "FINANCIAL_ASSERTIONS": [
      {
        "id": "EO",
        "confidence": 0.95,
        "keywords_matched": ["authorized", "transactions"],
        "aspect_addressed": "Transaction-Level - Authorization",
        "reasoning": "Authorization validates occurrence"
      },
      {
        "id": "A",
        "confidence": 0.90,
        "keywords_matched": ["accurately", "recorded"],
        "aspect_addressed": "Transaction-Level - Accuracy",
        "reasoning": "Accurate recording of amounts"
      }
    ],
    "COSO_ICFR": [
      {
        "id": "P10",
        "confidence": 0.88,
        "keywords_matched": ["control", "revenue"],
        "aspect_addressed": "Control Activities",
        "reasoning": "Revenue control activity"
      }
    ]
  },
  
  "primary_framework": "FINANCIAL_ASSERTIONS",
  "primary_criterion_id": "EO",
  "primary_confidence": 0.95,
  
  "financial_assertions": ["EO", "A"],
  "framework_category": "SOC1"
}
```

### CUEC with Multi-Framework Mappings (JSON)

```json
{
  "cuec_id": "CUEC-003",
  "cuec_description": "User must implement password complexity requirements",
  
  "framework_mappings": {
    "TSC": [
      {
        "id": "CC6.1",
        "confidence": 0.89,
        "reasoning": "Password policy is user responsibility"
      }
    ],
    "COSO": [
      {
        "id": "10",
        "confidence": 0.82,
        "reasoning": "User control activity"
      }
    ]
  },
  
  "primary_framework": "TSC",
  "primary_criterion_id": "CC6.1",
  "primary_confidence": 0.89,
  
  "cuec_tsc_mappings": [
    {"id": "CC6.1", "confidence": 0.89, "reasoning": "..."}
  ],
  
  "cuec_coso_mappings": [
    {"id": "10", "confidence": 0.82", "reasoning": "..."}
  ],
  
  "cuec_tsc_id": "CC6.1",
  "cuec_coso_id": "10",
  "cuec_closest_framework": "TSC"
}
```

## Database Schema (PostgreSQL)

### Control Table

```sql
CREATE TABLE control (
  id SERIAL PRIMARY KEY,
  control_id VARCHAR(128),
  control_desc TEXT,
  -- ... other control fields ...
  
  -- Multi-framework mapping (Phase 1 - NEW)
  framework_mappings JSONB,  -- {"TSC": [...], "COSO": [...], "FINANCIAL_ASSERTIONS": [...]}
  primary_framework VARCHAR(64),  -- "TSC", "COSO", "FINANCIAL_ASSERTIONS", etc.
  primary_criterion_id VARCHAR(128),  -- "CC6.1", "EO", "P10", etc.
  primary_confidence FLOAT,  -- 0.0-1.0
  
  -- Multi-match arrays (backward compatibility)
  control_tsc_mappings JSON,  -- [{"id": "CC6.1", "confidence": 0.92, ...}]
  control_coso_mappings JSON,  -- [{"id": "10", "confidence": 0.85, ...}]
  
  -- Legacy single-match fields (deprecated)
  control_tsc_id VARCHAR(128),
  control_coso_id VARCHAR(128),
  control_closest_framework VARCHAR(128),
  
  -- SOC1-specific
  financial_assertions JSON,  -- ["EO", "A", "C"]
  framework_category VARCHAR(32),  -- "SOC1", "SOC2", "BOTH", "AMBIGUOUS"
  
  scan_id INTEGER,
  -- ... other fields ...
);
```

### CUEC Table

```sql
CREATE TABLE cuec (
  id SERIAL PRIMARY KEY,
  cuec_seq INTEGER,
  cuec_description TEXT,
  -- ... other CUEC fields ...
  
  -- Multi-framework mapping (Phase 1 - NEW)
  framework_mappings JSONB,  -- {"TSC": [...], "COSO": [...]}
  primary_framework VARCHAR(64),
  primary_criterion_id VARCHAR(128),
  primary_confidence FLOAT,
  
  -- Multi-match arrays (backward compatibility)
  cuec_tsc_mappings JSON,  -- [{"id": "CC6.1", "confidence": 0.89, ...}]
  cuec_coso_mappings JSON,  -- [{"id": "10", "confidence": 0.82, ...}]
  
  -- Legacy single-match fields (deprecated)
  cuec_tsc_id VARCHAR(128),
  cuec_coso_id VARCHAR(128),
  cuec_closest_framework VARCHAR(128),
  
  scan_id INTEGER,
  -- ... other fields ...
);
```

## Data Flow

### 1. Extraction (Python)

**Control Extractor** (`backend/app/extractors/control_extractor.py`):
```python
# Line ~975-985
mapping_result = map_control_to_frameworks_dynamic(...)
db_fields = extract_mapping_fields_for_db(mapping_result)

control["framework_mappings"] = db_fields["framework_mappings"]
control["primary_framework"] = db_fields["primary_framework"]
control["primary_criterion_id"] = db_fields["primary_criterion_id"]
control["primary_confidence"] = db_fields["primary_confidence"]
control["control_tsc_mappings"] = db_fields.get("control_tsc_mappings", [])
control["control_coso_mappings"] = db_fields.get("control_coso_mappings", [])
control["control_closest_framework"] = db_fields["primary_framework"] or "Undetermined"
```

**CUEC Extractor** (`backend/app/extractors/cuec_extractor.py`):
```python
# Line ~445-455
mapping_result = map_cuec_to_frameworks_dynamic(...)

cuec['framework_mappings'] = mapping_result.get('framework_mappings', {})
cuec['primary_framework'] = mapping_result.get('primary_framework')
cuec['primary_criterion_id'] = mapping_result.get('primary_criterion_id')
cuec['primary_confidence'] = mapping_result.get('primary_confidence', 0.0)
cuec['cuec_tsc_mappings'] = mapping_result.get('framework_mappings', {}).get('TSC', [])
cuec['cuec_coso_mappings'] = mapping_result.get('framework_mappings', {}).get('COSO', [])
```

### 2. JSON Output

**Controls** saved to `data/json/control_result.json`:
```json
{
  "controls": [
    {
      "control_id": "...",
      "framework_mappings": {...},
      "primary_framework": "...",
      ...
    }
  ]
}
```

**CUECs** saved to `data/json/cuec_result.json`:
```json
{
  "cuecs": [
    {
      "cuec_description": "...",
      "framework_mappings": {...},
      "primary_framework": "...",
      ...
    }
  ]
}
```

### 3. Database Insertion

**Field Mapping** (`backend/app/config.py` - TABLE_FIELD_MAP):
```python
"control": [
    ...,
    "financial_assertions", "framework_category",
    "control_tsc_mappings", "control_coso_mappings",
    "framework_mappings", "primary_framework", "primary_criterion_id", "primary_confidence",
    ...
],
"cuec": [
    ...,
    "cuec_tsc_mappings", "cuec_coso_mappings",
    "framework_mappings", "primary_framework", "primary_criterion_id", "primary_confidence",
    ...
]
```

**Insert Logic** (`backend/app/explicit_sql_insert.py`):
```python
# Line ~268
values = [sanitize_value(ctrl.get(f)) for f in config.TABLE_FIELD_MAP["control"][:-1]] + [scan_id]
fields = config.TABLE_FIELD_MAP["control"]
sql = f"INSERT INTO control ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))})"
cur.execute(sql, values)
```

## Validation Checklist

- [x] **Control Extractor** outputs all framework mapping fields
- [x] **CUEC Extractor** outputs all framework mapping fields
- [x] **TABLE_FIELD_MAP** includes all new fields in correct order
- [x] **Database Schema** has all required columns (via Alembic migration `724d6ce5c265`)
- [x] **Field names** are consistent across extraction → JSON → database
- [x] **Data types** match (JSONB in DB, dict in Python, JSON in files)
- [x] **Legacy fields** maintained for backward compatibility
- [x] **SOC1 fields** (`financial_assertions`, `framework_category`) properly integrated

## Testing Verification

To verify data pipeline consistency:

1. **Extract Controls**:
   ```bash
   python test_scripts\test_quick_framework.py --soc2 "soc2_reports\Okta.pdf"
   ```

2. **Check JSON Output**:
   ```bash
   cat data\json\control_result.json | jq '.controls[0] | {framework_mappings, primary_framework, primary_criterion_id}'
   ```

3. **Verify Database**:
   ```sql
   SELECT 
     control_id,
     framework_mappings,
     primary_framework,
     primary_criterion_id,
     primary_confidence
   FROM control
   WHERE scan_id = <latest_scan_id>
   LIMIT 5;
   ```

4. **Validate CUEC Data**:
   ```sql
   SELECT 
     cuec_description,
     framework_mappings,
     primary_framework
   FROM cuec
   WHERE scan_id = <latest_scan_id>
   LIMIT 5;
   ```

## Notes

- **No Regex**: All framework matching uses GPT via `backend/app/frameworks/mapper.py`
- **Config Centralized**: All prompts, criteria, and settings in `backend/app/config.py`
- **Type Safety**: JSONB columns enforce JSON type in PostgreSQL
- **Backward Compatibility**: Legacy single-match fields (`control_tsc_id`, etc.) still populated for existing UI components

---

**Last Updated**: 2025-01-06
**Status**: ✅ Verified - Pipeline consistent from extraction to database
