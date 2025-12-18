# Schema Field Mapping & Gap Analysis

**Last Updated:** 2025-12-16  
**Purpose:** Comprehensive mapping of field names across database schema, SQLAlchemy models, extractor outputs, and INSERT configurations to identify mismatches and gaps.

---

## 1. CONTROL Table

### Database Schema (PostgreSQL)
```sql
Table "public.control"
- id (integer, PK, autoincrement)
- control_id (varchar 128)
- control_desc (text)
- control_test (text)
- control_test_results (text)
- control_line_ref (integer)
- control_seq (integer)
- control_status (varchar 64)
- merged_to_control_id (varchar 128)
- control_gpt_opinion (text)
- control_gpt_reasoning (text)
- control_confidence (double precision)
- confidence_calc (text)
- scan_id (integer)
- annotation (text)
- has_deviation (boolean)
- deviation_desc (text)
- verification_status (varchar 32)
- verification_metadata (json)
- pattern_confidence (double precision)
- final_confidence (double precision)
- control_page_refs (json)
- financial_assertions (json)
- framework_category (varchar 32)
- merge_history (json)
- is_duplicate_instance (boolean, default false)
- duplicate_group_id (varchar 128)
- instance_differentiator (json)
- framework_mappings (json)
- primary_framework (varchar 64)
- primary_criterion_id (varchar 128)
- primary_confidence (double precision)
- analyst_notes (text)
- deviation_summary (text)
- edit_log (text)
- updated_at (timestamp)
- updated_by_user_id (integer, FK to users.id)
```

### SQLAlchemy Model (models.py)
```python
class Control(Base):
    __tablename__ = "control"
    id = Column(Integer, primary_key=True, autoincrement=True)
    control_id = Column(String(128))
    control_desc = Column(Text)
    control_test = Column(Text)
    control_test_results = Column(Text)
    has_deviation = Column(Boolean)
    deviation_desc = Column(Text)
    control_page_refs = Column(JSON)
    control_line_ref = Column(Integer)
    control_seq = Column(Integer)
    
    financial_assertions = Column(JSON)
    framework_category = Column(String(32))
    
    framework_mappings = Column(JSON)
    primary_framework = Column(String(64))
    primary_criterion_id = Column(String(128))
    primary_confidence = Column(Float)
    
    control_status = Column(String(64))
    merged_to_control_id = Column(String(128))
    control_gpt_opinion = Column(Text)
    control_gpt_reasoning = Column(Text)
    control_confidence = Column(Float)
    confidence_calc = Column(Text)
    scan_id = Column(Integer)
    annotation = Column(Text)
    analyst_notes = Column(Text)
    edit_log = Column(Text)
    verification_status = Column(String(32))
    verification_metadata = Column(JSON)
    pattern_confidence = Column(Float)
    final_confidence = Column(Float)
    deviation_summary = Column(Text)
    merge_history = Column(JSON)
    is_duplicate_instance = Column(Boolean, default=False)
    duplicate_group_id = Column(String(128))
    instance_differentiator = Column(JSON)
```

### INSERT Field Mapping (config.py TABLE_FIELD_MAP)
```python
"control": [
    "control_id", "control_desc", "control_test", "control_test_results", 
    "has_deviation", "deviation_desc", "control_page_refs", "control_line_ref", "control_seq",
    "financial_assertions", "framework_category",
    "framework_mappings", "primary_framework", "primary_criterion_id", "primary_confidence",
    "control_status", "merged_to_control_id", "control_gpt_opinion", "control_gpt_reasoning", 
    "control_confidence", "confidence_calc", "scan_id"
]
```

### Extractor Output Fields (control_extractor_unified.py)
```python
# Expected fields from extractor:
{
    "control_id": str,
    "control_desc": str,
    "control_tests": [str],  # Note: plural in extractor
    "control_test_results": [str],  # Note: array in extractor
    "has_deviation": bool,
    "deviation_desc": str,
    "control_page_refs": [int],
    "control_line_ref": int,
    "control_confidence": float,
    "control_gpt_opinion": str,
    "control_gpt_reasoning": str,
    "confidence_calc": str,
    "continuation": bool,
    # Framework mappings added by separate step
}
```

### ⚠️ GAPS IDENTIFIED - Control Table

1. **~~MISSING IN MODEL~~** ✅ FIXED:
   - ~~`updated_at` (timestamp)~~ - Added to models.py
   - ~~`updated_by_user_id` (integer)~~ - Added to models.py

2. **MISSING FROM INSERT (Intentional - Manual Operation Fields Only):**
   - `annotation`, `analyst_notes`, `edit_log` - Set by manual user edits (NOT extractor outputs)
   - `deviation_summary` - Set by deviation router (manual summary)
   - `merge_history` - Set by merge service (auto/manual merges)
   - `is_duplicate_instance`, `duplicate_group_id`, `instance_differentiator` - Set by duplicate management router
   - **Note:** These fields are NOT set by extractors and correctly excluded from INSERT mapping

3. **✅ NOW IN INSERT (Extractor Outputs):**
   - ~~`verification_status`~~ - Added to TABLE_FIELD_MAP ✅
   - ~~`verification_metadata`~~ - Added to TABLE_FIELD_MAP ✅
   - ~~`pattern_confidence`~~ - Added to TABLE_FIELD_MAP ✅
   - ~~`final_confidence`~~ - Added to TABLE_FIELD_MAP ✅

4. **FIELD NAME MISMATCH:**
   - Extractor outputs `control_tests` (plural, array) → needs to be converted to `control_test` (singular, text) before insert
   - Extractor outputs `control_test_results` (array) → needs to be converted to text before insert

4. **RECENTLY FIXED ISSUES:**
   - ✅ `control_soc_domain` - Was in models.py but removed from database by migration d06f4f79d12a (FIXED: removed from model)
   - ✅ `pdf_snippet` - Was in TABLE_FIELD_MAP but removed from database by migration 04131ed40cc0 (FIXED: removed from config)

---

## 2. CUEC Table

### Database Schema (PostgreSQL)
```sql
Table "public.cuec"
- id (integer, PK, autoincrement)
- cuec_seq (integer)
- cuec_description (text)
- cuec_line_ref (integer)
- cuec_confidence (double precision)
- cuec_gpt_opinion (varchar 32)
- cuec_distance_from_cuec_keywords (integer)
- cuec_gpt_reasoning (text)
- cuec_justification (text)
- cuec_confidence_justification (text)
- scan_id (integer)
- annotation (text)
- control_strength (varchar 32)
- cuec_page_refs (json)
- framework_mappings (json)
- primary_framework (varchar 64)
- primary_criterion_id (varchar 128)
- primary_confidence (double precision)
- analyst_notes (text)
- edit_log (text)
```

### SQLAlchemy Model (models.py)
```python
class CUEC(Base):
    __tablename__ = "cuec"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cuec_seq = Column(Integer)
    cuec_description = Column(Text)
    cuec_line_ref = Column(Integer)
    cuec_page_refs = Column(JSON)
    cuec_confidence = Column(Float)
    cuec_gpt_opinion = Column(String(32))
    cuec_distance_from_cuec_keywords = Column(Integer)
    cuec_gpt_reasoning = Column(Text)
    cuec_justification = Column(Text)
    cuec_confidence_justification = Column(Text)
    
    framework_mappings = Column(JSON)
    primary_framework = Column(String(64))
    primary_criterion_id = Column(String(128))
    primary_confidence = Column(Float)
    
    scan_id = Column(Integer)
    annotation = Column(Text)
    analyst_notes = Column(Text)
    edit_log = Column(Text)
    control_strength = Column(String(32))
```

### INSERT Field Mapping (config.py TABLE_FIELD_MAP)
```python
"cuec": [
    "cuec_seq", "cuec_description", "cuec_line_ref", "cuec_page_refs", 
    "cuec_confidence", "cuec_gpt_opinion",
    "cuec_distance_from_cuec_keywords", "cuec_gpt_reasoning", 
    "cuec_justification", "cuec_confidence_justification",
    "framework_mappings", "primary_framework", "primary_criterion_id", "primary_confidence",
    "annotation", "control_strength", "scan_id"
]
```

### ⚠️ GAPS IDENTIFIED - CUEC Table

1. **~~MISSING FROM INSERT~~** ✅ FIXED:
   - ~~`analyst_notes`~~ - Added to TABLE_FIELD_MAP
   - ~~`edit_log`~~ - Added to TABLE_FIELD_MAP

2. **✅ GOOD:** Model and TABLE_FIELD_MAP are now fully aligned

3. **RECENTLY FIXED ISSUES:**
   - ✅ `pdf_snippet` - Was in TABLE_FIELD_MAP but removed from database by migration 04131ed40cc0 (FIXED: removed from config)

---

## 3. SUBSERVICE_ORG Table

### Database Schema (PostgreSQL)
```sql
Table "public.subservice_org"
- id (integer, PK, autoincrement)
- name (varchar 256)
- confidence (double precision)
- scan_id (integer)
- third_party_description (text)
- third_party_page_ref (text)
- third_party_confidence (double precision)
- distance_from_so_keywords (double precision)
- likely_so (varchar 64)
- common_so (varchar 64)
- source_context (text)
- confidence_justification (text)
- third_party_controls (json)
- annotation (text)
- analyst_notes (text)
- edit_log (text)
```

### SQLAlchemy Model (models.py)
```python
class SubserviceOrg(Base):
    __tablename__ = "subservice_org"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256))
    confidence = Column(Float)
    scan_id = Column(Integer)
    third_party_description = Column(Text)
    third_party_page_ref = Column(Text)
    third_party_confidence = Column(Float)
    distance_from_so_keywords = Column(Float)
    likely_so = Column(String(64))
    common_so = Column(String(64))
    source_context = Column(Text)
    confidence_justification = Column(Text)
    third_party_controls = Column(JSON)
```

### INSERT Field Mapping (config.py TABLE_FIELD_MAP)
```python
"subservice_org": ["name", "confidence", "scan_id"]
```

### ⚠️ GAPS IDENTIFIED - Subservice Org Table

1. **~~MISSING IN MODEL~~** ✅ FIXED:
   - ~~`annotation` (text)~~ - Added to models.py
   - ~~`analyst_notes` (text)~~ - Added to models.py
   - ~~`edit_log` (text)~~ - Added to models.py

2. **~~MISSING FROM INSERT~~** ✅ FIXED:
   - ~~All 12 enhanced fields~~ - All added to TABLE_FIELD_MAP
   - INSERT mapping expanded from 3 fields to 15 fields
   - Now saves: third_party_description, third_party_page_ref, third_party_confidence, distance_from_so_keywords, likely_so, common_so, source_context, confidence_justification, third_party_controls, annotation, analyst_notes, edit_log

3. **✅ RESOLVED:** Model and TABLE_FIELD_MAP now fully aligned with database schema

4. **RECENTLY FIXED ISSUES:**
   - ✅ `pdf_snippet` - Was in TABLE_FIELD_MAP but removed from database by migration 04131ed40cc0 (FIXED: removed from config)
   - ✅ Data loss prevented - Was only saving 3 of 16 fields (now saving 15 of 16)

---

## 4. COMPANY Table

### Database Schema (PostgreSQL)
```sql
Table "public.company"
- id (integer, PK, autoincrement)
- name (varchar 256, NOT NULL)
- parent_company (varchar 256)
- confidence (double precision)
- scan_id (integer)
- company_domain (varchar 256)
- logo_url (varchar 512)
```

### SQLAlchemy Model (models.py)
```python
class Company(Base):
    __tablename__ = "company"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    parent_company = Column(String(256))
    confidence = Column(Float)
    scan_id = Column(Integer)
    company_domain = Column(String(256), index=True)
    logo_url = Column(String(512))
```

### INSERT Field Mapping (config.py TABLE_FIELD_MAP)
```python
"company": ["name", "parent_company", "confidence", "scan_id", "company_domain", "logo_url"]
```

### ✅ STATUS - Company Table
**FULLY ALIGNED** - All fields match across database, model, and INSERT configuration.

---

## 5. PRODUCT Table

### Database Schema (PostgreSQL)
```sql
Table "public.product"
- id (integer, PK, autoincrement)
- name (varchar 256, NOT NULL)
- scan_id (integer)
```

### SQLAlchemy Model (models.py)
```python
class Product(Base):
    __tablename__ = "product"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    scan_id = Column(Integer)
```

### INSERT Field Mapping (config.py TABLE_FIELD_MAP)
```python
"product": ["name", "scan_id"]
```

### ✅ STATUS - Product Table
**FULLY ALIGNED** - All fields match across database, model, and INSERT configuration.

---

## 6. Summary of Critical Issues

### ✅ RESOLVED - Missing Model Definitions

1. **Control Table:** ✅ FIXED
   - ~~`updated_at` (timestamp)~~ - Added
   - ~~`updated_by_user_id` (integer, FK)~~ - Added

2. **Subservice Org Table:** ✅ FIXED
   - ~~`annotation` (text)~~ - Added
   - ~~`analyst_notes` (text)~~ - Added
   - ~~`edit_log` (text)~~ - Added

### ✅ ALL CRITICAL GAPS RESOLVED

1. **Control Table:** ✅ FULLY ALIGNED
   - ~~`verification_status`, `verification_metadata`, `pattern_confidence`, `final_confidence`~~ - Added to TABLE_FIELD_MAP (extractor outputs)
   - Manual operation fields correctly excluded: `deviation_summary`, `merge_history`, `is_duplicate_instance`, `duplicate_group_id`, `instance_differentiator`, `annotation`, `analyst_notes`, `edit_log`
   - **All extractor outputs now properly saved**

2. **CUEC Table:** ✅ FULLY ALIGNED
   - ~~`analyst_notes`, `edit_log`~~ - Added to TABLE_FIELD_MAP

3. **Subservice Org Table:** ✅ FULLY ALIGNED
   - ~~ALL enhanced fields~~ - Expanded from 3 to 15 fields in TABLE_FIELD_MAP
   - Data loss from subservice_orgs_extractor now prevented

### 🟢 LOW PRIORITY - Documentation

1. Extractor output field schemas should be formally documented
2. Field transformation rules (e.g., `control_tests` → `control_test`) should be documented

---

## 7. Recommended Actions

### ✅ Completed (2025-12-16)

1. **✅ DONE - Added missing model columns:**
   - Control: `updated_at`, `updated_by_user_id` (added to models.py)
   - SubserviceOrg: `annotation`, `analyst_notes`, `edit_log` (added to models.py)

2. **✅ DONE - Expanded subservice_org INSERT mapping:**
   - Increased from 3 fields to 15 fields in TABLE_FIELD_MAP
   - Now captures all extractor data: third_party_description, confidence scores, controls, etc.

3. **✅ DONE - Added analyst fields to CUEC INSERT mapping:**
   - Added `analyst_notes` and `edit_log` to TABLE_FIELD_MAP

### Short-term (This Week)

4. **✅ DONE - Added verification/pattern fields to control INSERT mapping:**
   - Confirmed extractors (control_extractor_combined.py) populate these fields
   - Added to TABLE_FIELD_MAP: verification_status, verification_metadata, pattern_confidence, final_confidence
   - These are core extractor outputs for 5-factor confidence scoring

### ✅ Medium-term (Completed 2025-12-16)

5. **✅ DONE - Created automated schema validation test:**
   - Created `backend/app/tests/test_schema_validation.py`
   - Validates database schema vs models vs INSERT mappings
   - Catches mismatches automatically with clear error messages
   - Can be run as part of CI/CD: `pytest test_schema_validation.py -v`

6. **✅ DONE - Documented extractor output schemas:**
   - Created `docs/EXTRACTOR_OUTPUT_SCHEMAS.md`
   - Complete field-by-field documentation for all extractors
   - Includes data types, validation rules, and transformation notes
   - Documents which fields are NOT in extractor output

7. **✅ DONE - Added field transformation documentation:**
   - Created `docs/FIELD_TRANSFORMATIONS.md`
   - Documents all data transformations (array→text, aggregations, etc.)
   - Includes debugging tips and transformation order
   - Lists critical transformations with rationale

---

## 8. Validation Checklist

Use this checklist when adding new fields:

- [ ] Database schema updated (Alembic migration)
- [ ] SQLAlchemy model updated (models.py)
- [ ] INSERT mapping updated (config.py TABLE_FIELD_MAP)
- [ ] Extractor outputs the field (if applicable)
- [ ] Field transformation documented (if name differs between extractor and database)
- [ ] Frontend ready to display the field (if user-facing)

---

## 9. Recent Fixes Log

| Date | Issue | Resolution |
|------|-------|------------|
| 2025-12-16 | `control_soc_domain` in models.py but removed from DB | Removed from models.py line 76 |
| 2025-12-16 | `pdf_snippet` in TABLE_FIELD_MAP but removed from DB | Removed from config.py lines 2554, 2562 |
| 2025-12-16 | `idx` NameError in explicit_sql_insert.py | Added enumerate() to loop at line 298 |
| 2025-12-16 | Missing `updated_at`, `updated_by_user_id` in Control model | Added to models.py |
| 2025-12-16 | Missing `annotation`, `analyst_notes`, `edit_log` in SubserviceOrg model | Added to models.py |
| 2025-12-16 | Subservice_org INSERT only saved 3 of 16 fields | Expanded TABLE_FIELD_MAP from 3 to 15 fields |
| 2025-12-16 | CUEC INSERT missing analyst fields | Added `analyst_notes`, `edit_log` to TABLE_FIELD_MAP |
| 2025-12-16 | Control INSERT missing verification fields | Added `verification_status`, `verification_metadata`, `pattern_confidence`, `final_confidence` to TABLE_FIELD_MAP |
| 2025-12-16 | Created automated schema validation test | Created test_schema_validation.py with comprehensive alignment checks |
| 2025-12-16 | Documented extractor output schemas | Created EXTRACTOR_OUTPUT_SCHEMAS.md with field-by-field documentation |
| 2025-12-16 | Documented field transformations | Created FIELD_TRANSFORMATIONS.md with transformation rules and debugging tips |

---

**END OF MAPPING DOCUMENT**
