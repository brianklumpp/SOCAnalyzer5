# GPT Model Configuration

## Current Setup

### What Model is Running?

**Answer: GPT-4o** (not GPT-5)

The configuration uses "gpt-5" as a **logical name** in the code, but it maps to the actual available model `gpt-4o` in Dataiku.

## Configuration Flow

```
Code requests "gpt-5"
    ↓
config.py: DEFAULT_GPT_MODEL = "gpt-5"
    ↓
config.py: DATAIKU_CATALOG_MAP["gpt-5"] = <env var DATAIKU_LLM_GPT5>
    ↓
.env: DATAIKU_LLM_GPT5 = "azureopenai:Azure-OpenAI-Prod:gpt-4o"
    ↓
Dataiku runs: gpt-4o model
```

## Configuration Files

### 1. `.env` (line 34)
```bash
DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-4o
```
This is the **actual model ID** that Dataiku uses. Currently set to `gpt-4o` because GPT-5 is not deployed.

### 2. `backend/app/config.py` (line 87)
```python
"gpt-5": os.getenv("DATAIKU_LLM_GPT5", "azureopenai:Azure-OpenAI-Prod:gpt-4o")
```
Maps the logical name "gpt-5" to the Dataiku LLM ID.

### 3. `backend/app/config.py` (line 594)
```python
DEFAULT_GPT_MODEL = "gpt-5"
```
All extractors use this as their default model.

## Why This Design?

This abstraction allows you to:
- Change the underlying model without touching code
- Switch models by just updating the `.env` file
- Use different models for different environments
- Prepare for GPT-5 when it becomes available (just update `.env`)

## Available Models

According to testing (`test_gpt5_variations.py`):

| Model Name | Status | Catalog ID |
|------------|--------|------------|
| gpt-4o | ✅ Available | `azureopenai:Azure-OpenAI-Prod:gpt-4o` |
| gpt-4o-mini | ✅ Available | `azureopenai:Azure-OpenAI-Prod:gpt-4o-mini` |
| gpt-5 | ❌ Not Deployed | N/A |
| o1-preview | ❌ Not Deployed | N/A |
| o1-mini | ❌ Not Deployed | N/A |

## Changing Models

### Option 1: Use GPT-4o-mini (faster, cheaper)
```bash
# In .env file:
DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-4o-mini
```

### Option 2: When GPT-5 becomes available
```bash
# In .env file (after it's deployed in Dataiku):
DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-5
```

### Option 3: Rename to be less confusing
```python
# In config.py, change:
DEFAULT_GPT_MODEL = "gpt-4o"

# And in .env:
DATAIKU_LLM_GPT4O=azureopenai:Azure-OpenAI-Prod:gpt-4o
```

## Verification

Interactive mode shows which model is being used:

```
GPT Model Configuration
────────────────────────────────────────────────
ℹ Configured model: gpt-5
ℹ Actual model being used: gpt-4o
ℹ Dataiku LLM ID: azureopenai:Azure-OpenAI-Prod:gpt-4o
```

## Embedding Refactor

**Previous:** System used OpenAI embeddings (`text-embedding-ada-002`) for TSC/COSO framework mapping via cosine similarity.

**Current:** Pure GPT-based framework mapping (Path C implementation).

### Why the Change?

1. **Single Dependency** - Dataiku DSS only (no OpenAI API needed)
2. **Unified DNS Fallback** - All API calls go through existing Dataiku DNS fallback
3. **Better Accuracy** - GPT-5 can reason about control intent vs simple embedding similarity
4. **Simpler Code** - Removed embedding cache, numpy, certifi, requests imports
5. **Clear Failures** - GPT errors handled consistently

### Performance Impact

**Previous Architecture:**
- Control extraction: 175 controls × 3 GPT + 175×2 embeddings = ~875 API calls
- CUEC extraction: 16 CUECs × 1 GPT + 16×2 embeddings = ~48 API calls

**New Architecture:**
- Control extraction: 175 controls × 3 GPT = 525 API calls (no embeddings)
- CUEC extraction: 16 CUECs × 2 GPT = 32 API calls

**Result:** ~30% reduction in API calls, all to single endpoint

### Framework Mapping Prompt

GPT now selects best-matching framework criterion:

```python
You are an expert SOC 2 auditor. Select the single best-matching {framework_name} criterion for this control.

Control Description:
{control_desc}

Available {framework_name} Criteria:
- CC7.2: Description...
- CC10.1: Description...

Respond with JSON:
- best_id: The ID of the best-matching criterion
- confidence: Confidence level from 0.0 to 1.0
- reasoning: Brief explanation
```

## Cleanup Behavior

Both `interactive_scan.py` and `run_analysis.py` now **automatically clean up** before each run:

### What Gets Cleared:
1. **Checkpoint file** - `_extraction_checkpoint.json`
2. **JSON results** - All `*_result.json` files
3. **Log files** - All `.log` files truncated

### Why?
- Prevents stale data from previous runs
- Ensures checkpoint doesn't skip extractors
- Makes debugging easier with clean logs
- Every run is a fresh start

## Troubleshooting

### Error: "LLM azureopenai:Azure-OpenAI-Prod:gpt-5 is not available"
**Solution:** Update `.env` to use `gpt-4o` instead

### Check available models:
```powershell
python test_gpt5_variations.py
```

### Verify configured model:
```python
from app.config import DATAIKU_CATALOG_MAP, DEFAULT_GPT_MODEL
print(f"Model: {DEFAULT_GPT_MODEL}")
print(f"Actual: {DATAIKU_CATALOG_MAP[DEFAULT_GPT_MODEL]}")
```

### DNS/Connection Errors
See **DNS Configuration** guide for Dataiku DSS DNS fallback setup.

## Further Reading

- See **DNS Configuration** for connection troubleshooting
- See **V4 Extraction Architecture** for how GPT models are used
- See **Architecture > Backend Services** for GPT client implementation
