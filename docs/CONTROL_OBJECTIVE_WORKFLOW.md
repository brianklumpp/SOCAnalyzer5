# Control Objective Extraction System - Complete Workflow Documentation

> **Document Links:** Add comments `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step N -->` in code at locations specified below for easy reference.

## 1. Overview

The Control Objective Extraction system automatically identifies and extracts control objectives from SOC 1 and SOC 2 audit reports. It uses GPT-powered extraction with multi-factor confidence scoring to distinguish objectives (strategic goals/outcomes) from controls (tactical activities) and CUECs (user entity controls).

**Why it exists:**
- Audit reports contain 1000s of different formats for objectives
- No reliable regex patterns exist across reports
- GPT provides semantic understanding to handle variation
- Enables automatic control-to-objective mapping for compliance tracking
- Provides confidence-based filtering for analyst review

---

## 2. System Architecture

### Docker Containers

| Container | IP Address | Port | Purpose |
|-----------|------------|------|---------|
| `socanalyzer-backend` | 172.20.0.5 | 8000 | FastAPI backend, runs extractors |
| `socanalyzer-postgres` | 172.20.0.3 | 5432 (exposed as 5433) | PostgreSQL database |
| `socanalyzer-redis` | 172.20.0.4 | 6379 | Job tracking, progress updates |
| `socanalyzer-dns-cache` | 172.20.0.2 | 53 | DNS caching for corporate networks |

### Database Connections

**From docker-compose.yml:**
```yaml
DATABASE_URL_ASYNC: postgresql+asyncpg://soc2_analyzer:puntitforthewin@172.20.0.3:5432/soc2analyzer
DATABASE_URL_SYNC: postgresql://soc2_analyzer:puntitforthewin@172.20.0.3:5432/soc2analyzer
```

**Host access:** `localhost:5433` → `172.20.0.3:5432`

### File Locations

| Component | Path |
|-----------|------|
| Main Extractor | backend/app/extractors/objective_extractor.py |
| Configuration | backend/app/config.py |
| Database Models | backend/app/models.py |
| Main API Router | backend/app/routers/objective_router.py |
| PDF Handler | backend/app/pdf_handler.py |

---

## 3. Database Schema

### Table: `control_objectives`

```python
# Primary identification
id = Column(Integer, primary_key=True, autoincrement=True)
scan_id = Column(Integer, ForeignKey('scan.id', ondelete='CASCADE'), nullable=False, index=True)
objective_id_normalized = Column(String(128), nullable=True, index=True)  # e.g., "CC6.1"
objective_text = Column(Text, nullable=False)

# Multi-factor confidence (0.0-1.0)
keyword_confidence = Column(Float, default=0.0)      # Weight: 0.25
distance_confidence = Column(Float, default=0.0)     # Weight: 0.20
gpt_confidence = Column(Float, default=0.0)          # Weight: 0.30
alignment_confidence = Column(Float, default=0.0)    # Weight: 0.15
format_confidence = Column(Float, default=0.0)       # Weight: 0.10
final_confidence = Column(Float, nullable=False, index=True)  # Weighted average

# Source metadata
page_refs = Column(JSON)             # [12, 13]
line_ref = Column(Integer)           # Document line number

# Status (default='pending')
status = Column(String(32), default='pending')  # 'pending', 'approved', 'rejected'
```

### Key SQL Queries

**Check extraction results:**
```sql
SELECT 
    status,
    COUNT(*) as count,
    ROUND(AVG(final_confidence)::numeric, 2) as avg_confidence
FROM control_objectives
WHERE scan_id = <scan_id>
GROUP BY status;
```

**Find boundary violations (zero confidence):**
```sql
SELECT objective_id_normalized, line_ref, objective_text
FROM control_objectives
WHERE scan_id = <scan_id> AND final_confidence = 0.0;
```

---

## 4. Complete Extraction Pipeline

### **STEP 1: Section Boundary Enforcement**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 707-747  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 1 -->`

**What:** Filters full extracted text to ONLY the Control_Descriptions section.

**Input:** Full PDF text, sections array with boundaries  
**Output:** Filtered text, start_line, end_line  
**Critical:** Raises ValueError if Control_Descriptions section missing

---

### **STEP 2: Text Chunking**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 749-783  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 2 -->`

**What:** Splits filtered text into overlapping chunks (600 tokens per chunk, 120 token overlap).

**Output:** List of (chunk_text, chunk_start_line) tuples

---

### **STEP 3: GPT Extraction**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 176-215  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 3 -->`

**What:** Extracts objectives from each chunk using GPT (OBJECTIVE_EXTRACTION_PROMPT).

**Output:** JSON with objectives array (id, text, line_ref, confidence)  
**Critical:** line_ref is chunk-relative (0-based within chunk)

---

### **STEP 4: Line_ref Adjustment**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 205-210, `backend/app/main.py` lines 792-796  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 4 -->`

**What:** Converts chunk-relative line_ref to document-relative.

**Formula:**
```python
document_chunk_start = start_line + chunk_start_line
obj['line_ref'] = document_chunk_start + obj['line_ref']
```

---

### **STEP 5: Deduplication**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 220-263  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 5 -->`

**What:** Merges exact duplicates from overlapping chunks using GPT.

**Target:** Keep 95-99% of objectives (most should be unique)

---

### **STEP 6: Control Filtering**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 837-865  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 6 -->`

**What:** Removes controls misclassified as objectives (action verbs, test descriptions).

---

### **STEP 7: GPT Validation (NEW)**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 1064-1092  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 7 -->`

**What:** GPT-based semantic validation replacing strict regex patterns.

**Validates:** ID format flexibility (CC1.1, HR-01, SEC-023, etc.), text quality, semantic correctness  
**Fallback:** Accept with 0.15 confidence penalty on API error  
**Reason:** Supports 1000s of different SOC1/SOC2 formats

---

### **STEP 8: Boundary Validation (FINAL AUTHORITY)**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 1094-1115  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 8 -->`

**What:** Validates line_ref within Control_Descriptions section boundaries.

**Action:** If line_ref < start_line OR line_ref > end_line → confidence = 0%  
**Priority:** Boundary check OVERRULES GPT validation  
**Result:** Zero-confidence objectives go to Low Confidence table for manual review

---

### **STEP 9: Database Save with Auto-Approval**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 1148-1166  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 9 -->`

**What:** Saves objectives to database, auto-approves if confidence >= 65%.

**Logic:**
```python
if obj_model.final_confidence >= 0.65:
    obj_model.status = 'approved'
else:
    obj_model.status = 'pending'
```

---

### **STEP 10: Page Ref Calculation**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 1003-1022  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 10 -->`

**What:** Converts line_ref to page_refs using "=== PAGE X ===" markers.

---

### **STEP 11: Mapping to Controls**
📍 **Location:** `backend/app/extractors/objective_extractor.py` lines 1168-1183  
📝 **Code comment:** `<!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 11 -->`

**What:** Creates automatic control-objective mappings based on proximity and GPT alignment.

---

## 5. Validation Strategy

### Why GPT Instead of Regex?

**Problem:** 1000s of different SOC1/SOC2 formats exist:
- Trust Services: CC1.1, CC2.1, A1.2, PI1.3
- Custom: HR-01, IAM-1, SEC-023, OBJ-123
- Variations: "CC 1.1", "CC1.1:", "CC1.1 -", unnumbered objectives

**Regex Limitations:**
- Cannot handle semantic differences (objective vs control)
- Brittle to format variations
- Rejects valid objectives with non-standard IDs

**GPT Advantages:**
- Semantic understanding (WHAT vs HOW)
- Handles format variations naturally
- Adapts to new report formats without code changes

### Confidence Penalty for API Failures

When GPT validation API fails:
```python
# Accept objective with 0.15 confidence reduction
final_confidence = max(0.0, final_confidence - 0.15)
```

Better to have low-confidence objective for review than lose valid data.

### Boundary Check as Final Authority

**Priority:** Boundary check OVERRULES everything else
- Section boundaries are definitive (from TOC detection)
- If outside Control_Descriptions → confidence = 0% (appears in Low Confidence table)

---

## 6. Troubleshooting Guide

### PowerShell Commands

**View extraction logs:**
```powershell
# Real-time objective extraction
docker logs -f socanalyzer-backend | Select-String "OBJECTIVES|VALIDATION"

# Check rejections
docker logs socanalyzer-backend --tail 500 | Select-String "REJECTED"

# Boundary violations
docker logs socanalyzer-backend --tail 500 | Select-String "BOUNDARY_CHECK"

# GPT validation calls
docker logs socanalyzer-backend --tail 500 | Select-String "GPT_VALIDATION"
```

### Common Issues

**Issue: Only 10/38 objectives extracted**
```powershell
# Check what was rejected
docker logs socanalyzer-backend --tail 500 | Select-String "REJECTED|PATTERN|BOUNDARY"
```

**Expected causes:**
- Pattern validation too strict (fixed with GPT validation)
- Boundary violations (check section boundaries in scan.result_json)
- Control filtering too aggressive

**Issue: All objectives zero confidence**
```sql
SELECT COUNT(*) FROM control_objectives 
WHERE scan_id = 2 AND final_confidence = 0.0;
```

Likely cause: All objectives outside section boundaries (check start_line/end_line)

---

## 7. Configuration

### Key Settings (backend/app/config.py)

```python
# Objective extraction toggle
ENABLE_OBJECTIVE_EXTRACTION = True

# GPT model (recommended: gpt-4o or gpt-5)
CONTROL_OBJECTIVES_MODEL = "gpt-4o"

# Chunking
OBJECTIVE_TOKENS_PER_CHUNK = 600         # ~2400 chars
OBJECTIVE_CHUNK_OVERLAP_TOKENS = 120     # ~480 chars overlap

# Auto-approval threshold
AUTO_APPROVE_THRESHOLD = 0.65  # >= 65% → status='approved'
```

---

## 8. Performance Metrics

### Expected Timing

| Metric | Value |
|--------|-------|
| Chunks per scan | 15-30 |
| GPT calls per scan | 38+ (extraction + dedup + validation) |
| Total extraction time | 45-90 seconds |
| Objectives extracted | 30-60 (typical SOC2) |
| Auto-approval rate | 70-85% |

### Validation Performance Monitoring

```powershell
# Track validation duration
docker logs socanalyzer-backend --tail 500 | Select-String "VALIDATION.*completed in"
```

**Threshold:** >30 seconds = consider batching optimization

---

## Code Comment Insertion Guide

Add these comments in **backend/app/extractors/objective_extractor.py**:

```python
# Line 707 (before section filtering):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 1 -->

# Line 749 (before chunking):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 2 -->

# Line 176 (in extract_objectives_from_chunk):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 3 -->

# Line 792 (in main extraction loop, main.py):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 4 -->

# Line 220 (deduplicate_objectives function):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 5 -->

# Line 837 (before control filtering):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 6 -->

# Line 1064 (before validation):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 7 -->

# Line 1094 (before boundary validation):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 8 -->

# Line 1148 (before database save):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 9 -->

# Line 1003 (before page ref calculation):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 10 -->

# Line 1168 (before control mapping):
# <!-- DOC: See CONTROL_OBJECTIVE_WORKFLOW.md Section 4 Step 11 -->
```

---

**Document Version:** 1.0  
**Last Updated:** February 10, 2026  
**Maintained By:** SOC Analyzer Development Team
