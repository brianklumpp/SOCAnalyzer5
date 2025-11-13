# Embedding Refactor - Path C Implementation

**Date:** November 11, 2025  
**Status:** ✅ Complete - Ready for Testing

## Problem Statement

The original architecture used **OpenAI embeddings** (`text-embedding-ada-002`) for TSC/COSO framework mapping via cosine similarity. This created multiple issues:

1. **Dual API Dependencies**: Both Dataiku DSS (for GPT) and OpenAI (for embeddings)
2. **DNS Failures**: OpenAI API calls failed when corporate DNS was down (no DNS fallback)
3. **Fragmented HTTP Clients**: GPT calls used `gpt_client.py`, embeddings used raw `requests.post()`
4. **Silent Failures**: Embedding errors cascaded into extraction failures without clear visibility
5. **Limited Accuracy**: Cosine similarity on embeddings less accurate than GPT reasoning for framework alignment

### Error Examples

```
2025-11-11 04:38:40 | ERROR | gaierror(-3, 'Temporary failure in name resolution')
2025-11-11 04:38:56 | ERROR | Failed to get embedding for control_desc
```

## Solution: Path C - Pure GPT-Based Framework Mapping

Replaced OpenAI embeddings + cosine similarity with **direct GPT-5 reasoning** via Dataiku DSS.

### Benefits

✅ **Single Dependency**: Dataiku DSS only (no OpenAI API needed)  
✅ **Unified DNS Fallback**: All API calls go through existing Dataiku DNS fallback  
✅ **Better Accuracy**: GPT-5 can reason about control intent vs simple embedding similarity  
✅ **Simpler Code**: Removed embedding cache, numpy, certifi, requests imports  
✅ **Clear Failures**: GPT errors handled consistently through existing logging  

## Changes Made

### 1. Control Extractor (`control_extractor_v2.py`)

**Removed:**
- `get_openai_embedding()` function (lines 1114-1150)
- `cosine_similarity()` function (lines 1152-1156)
- `_embedding_cache` global dict
- Imports: `requests`, `certifi` (inline imports)
- Dependency on `EMBEDDING_PROVIDER`, `OPENAI_EMBEDDING_MODEL` config

**Added:**
- `_select_best_framework_match_with_gpt()` - New GPT-based selection function
- Uses GPT prompt with control description + top 10 framework candidates
- Returns `(best_id, confidence)` instead of `(best_id, similarity_score)`

**Refactored:**
- `map_control_to_frameworks()` now uses pure GPT reasoning
- Flow: GPT domain classification → filter candidates → GPT selects best match
- Confidence scores (0.0-1.0) replace cosine similarity scores

### 2. CUEC Extractor (`cuec_extractor.py`)

**Removed:**
- `get_openai_embedding()` function (lines 887-916)
- `cosine_similarity()` function (lines 918-922)
- `_embedding_cache` global dict
- `import numpy as np`
- `OPENAI_EMBEDDING_MODEL`, `OPENAI_EMBEDDING_URL` constants

**Refactored:**
- `map_cuec_to_frameworks()` now uses single GPT prompt for both TSC and COSO
- Combines both framework selections into one API call for efficiency
- Returns confidence scores instead of similarity scores

### 3. Config (`config.py`)

**Updated:**
- `EMBEDDING_PROVIDER` default changed from `"openai"` to `"gpt"` (for backwards compat)
- Added deprecation comments explaining embeddings no longer used
- Kept variables for backwards compatibility but marked as having no effect
- `CONTROL_EMBEDDING_MAPPING_ENABLED` still controls whether framework mapping happens

## GPT Prompt Design

### Framework Selection Prompt

```python
You are an expert SOC 2 auditor. Select the single best-matching {framework_name} criterion for this control.

Control Description:
{control_desc}

Available {framework_name} Criteria:
- CC7.2: Description...
- CC10.1: Description...
...

Respond ONLY with a JSON object with keys:
- best_id: The ID of the best-matching criterion (must be from the list above)
- confidence: Your confidence level from 0.0 to 1.0
- reasoning: Brief explanation of why this criterion matches best
```

### Validation

- GPT must select from provided candidates (validated against ID list)
- Invalid IDs logged and return `None, -1`
- Errors handled gracefully with fallback to no mapping

## Testing Checklist

### Unit Testing

- [x] No syntax errors in refactored files
- [x] No import errors on backend startup
- [x] Container rebuild succeeds

### Integration Testing

- [ ] Control extraction completes for 175 controls
- [ ] No DNS failures during extraction
- [ ] TSC/COSO mappings present in control_result.json
- [ ] CUEC extraction completes with framework mappings
- [ ] Confidence scores in range 0.0-1.0
- [ ] No OpenAI API calls in logs

### Regression Testing

- [ ] Subservice orgs extraction works (wrapper function fix)
- [ ] All other extractors (company, auditor, product, dates) unchanged
- [ ] Frontend displays framework mappings correctly
- [ ] Export functionality works with new confidence scores

## Performance Considerations

**Previous Architecture:**
- Control extraction: 175 controls × 3 GPT calls + 175×2 embedding calls = ~875 API calls
- CUEC extraction: 16 CUECs × 1 GPT + 16×2 embedding calls = ~48 API calls

**New Architecture:**
- Control extraction: 175 controls × 3 GPT calls = 525 API calls (no embeddings)
- CUEC extraction: 16 CUECs × 2 GPT calls = 32 API calls (combined TSC/COSO in one call)

**Result:** ~30% reduction in API calls, all to single endpoint (Dataiku DSS)

## Rollback Plan

If GPT-based mapping doesn't work:

1. Restore from git: `git checkout HEAD -- backend/app/extractors/`
2. Rebuild containers: `.\socanalyzer.ps1 rebuild`
3. Or disable framework mapping: `CONTROL_EMBEDDING_MAPPING_ENABLED=false`

## Next Steps

1. ✅ Rebuild containers (completed - 11.8s build time)
2. ✅ Verify clean startup (completed - no errors)
3. ⏳ Run full extraction test
4. ⏳ Verify TSC/COSO mappings accuracy
5. ⏳ Test subservice extraction (wrapper function fix)
6. ⏳ Compare mapping quality vs previous embedding approach

## Related Files

- `backend/app/extractors/control_extractor_v2.py` (1305 lines → simplified)
- `backend/app/extractors/cuec_extractor.py` (967 lines → simplified)
- `backend/app/config.py` (embedding config deprecated)
- `backend/app/gpt_client.py` (unchanged - existing DNS fallback works)

## Success Metrics

- **Primary:** Full extraction completes without DNS errors
- **Secondary:** TSC/COSO mappings present and accurate
- **Tertiary:** Extraction time comparable or faster than embedding approach
