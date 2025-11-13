# GPT Model Configuration

## Current Setup (As of November 11, 2025)

### What Model is Actually Running?

**Answer: GPT-4o** (not GPT-5)

### Why the Confusion?

The configuration uses "gpt-5" as a **logical name** in the code, but it maps to the actual available model `gpt-4o` in Dataiku.

### Configuration Flow

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

### Key Files

1. **`.env` (line 34)**
   ```
   DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-4o
   ```
   - This is the **actual model ID** that Dataiku uses
   - Currently set to `gpt-4o` because GPT-5 is not deployed in the Azure-OpenAI-Prod connection

2. **`backend/app/config.py` (line 87)**
   ```python
   "gpt-5": os.getenv("DATAIKU_LLM_GPT5", "azureopenai:Azure-OpenAI-Prod:gpt-4o")
   ```
   - Maps the logical name "gpt-5" to the Dataiku LLM ID

3. **`backend/app/config.py` (line 594)**
   ```python
   DEFAULT_GPT_MODEL = "gpt-5"
   ```
   - All extractors use this as their default model

### Why This Design?

This abstraction allows you to:
- Change the underlying model without touching code
- Switch models by just updating the `.env` file
- Use different models for different environments
- Prepare for GPT-5 when it becomes available (just update `.env`)

### How to Change Models

**Option 1: Use GPT-4o-mini (faster, cheaper)**
```bash
# In .env file:
DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-4o-mini
```

**Option 2: When GPT-5 becomes available**
```bash
# In .env file (after it's deployed in Dataiku):
DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-5
```

**Option 3: Rename to be less confusing**
```python
# In config.py, change:
DEFAULT_GPT_MODEL = "gpt-4o"

# And in .env:
DATAIKU_LLM_GPT4O=azureopenai:Azure-OpenAI-Prod:gpt-4o
```

### Available Models in Dataiku

According to our testing (`test_gpt5_variations.py`):

| Model Name | Status | Catalog ID |
|------------|--------|------------|
| gpt-4o | ✅ Available | `azureopenai:Azure-OpenAI-Prod:gpt-4o` |
| gpt-4o-mini | ✅ Available | `azureopenai:Azure-OpenAI-Prod:gpt-4o-mini` |
| gpt-5 | ❌ Not Deployed | N/A |
| o1-preview | ❌ Not Deployed | N/A |
| o1-mini | ❌ Not Deployed | N/A |

### Verification

The interactive mode now shows which model is being used at startup:

```
GPT Model Configuration
────────────────────────────────────────────────
ℹ Configured model: gpt-5
ℹ Actual model being used: gpt-4o
ℹ Dataiku LLM ID: azureopenai:Azure-OpenAI-Prod:gpt-4o
```

### Troubleshooting

**Error: "LLM azureopenai:Azure-OpenAI-Prod:gpt-5 is not available"**
- This means GPT-5 is not deployed in your Dataiku connection
- Solution: Update `.env` to use `gpt-4o` instead

**How to check available models:**
```powershell
python test_gpt5_variations.py
```

**How to verify which model is configured:**
```python
from app.config import DATAIKU_CATALOG_MAP, DEFAULT_GPT_MODEL
print(f"Model: {DEFAULT_GPT_MODEL}")
print(f"Actual: {DATAIKU_CATALOG_MAP[DEFAULT_GPT_MODEL]}")
```

---

## Cleanup Behavior (New as of Nov 11, 2025)

Both `interactive_scan.py` and `run_analysis.py` now **automatically clean up** before each run:

### What Gets Cleared:
1. **Checkpoint file**: `data/json/_extraction_checkpoint.json`
2. **JSON results**:
   - `section_results.json`
   - `combined_result.json`
   - `control_result.json`
   - `cuec_result.json`
   - `subservice_orgs_result.json`
   - `product_result.json`
   - `auditor_result.json`
   - `company_result.json`
   - `report_date_result.json`
   - `coverage_period_result.json`

3. **Log files**: All `.log` files in `data/logs/` are truncated (cleared but not deleted)

### Why?
- Prevents stale data from previous runs
- Ensures checkpoint doesn't skip extractors
- Makes debugging easier with clean logs
- Every run is a fresh start

### Disable Cleanup (if needed)
Comment out the cleanup section in the `run_analysis()` function if you want to preserve previous run data.
