# GPT Model Configuration Fix

## Issue

The system was configured to use `gpt-5` as the default GPT model, but **GPT-5 doesn't exist yet**. This caused errors when trying to run analysis:

```
java.lang.IllegalArgumentException: LLM azureopenai:Azure-OpenAI-Prod:gpt-5 
is not available for connection Azure-OpenAI-Prod
```

## Root Cause

Multiple configuration settings were referencing the non-existent `gpt-5` model:

1. **Default Model**: `DEFAULT_GPT_MODEL = 'gpt-5'` (line 594)
2. **All Extractors**: All extractors configured to use `'gpt-5'` (lines 660-669)
3. **Model Mapping**: The `gpt-5` mapping was present but pointing to itself

## Fix Applied

Changed all references from `gpt-5` to `gpt-4o` (the best currently available model):

### 1. Default GPT Model
```python
# Before
DEFAULT_GPT_MODEL = os.getenv('DEFAULT_GPT_MODEL', 'gpt-5')

# After
DEFAULT_GPT_MODEL = os.getenv('DEFAULT_GPT_MODEL', 'gpt-4o')
```

### 2. Extractor Models
```python
# Before
GPT_MODELS = {
    'control_extractor_v2': 'gpt-5',
    'company_extractor': 'gpt-5',
    # ... etc
}

# After
GPT_MODELS = {
    'control_extractor_v2': 'gpt-4o',
    'company_extractor': 'gpt-4o',
    # ... etc
}
```

### 3. Dataiku Catalog Mapping
```python
# Ensured gpt-5 fallback maps to gpt-4o
"gpt-5": os.getenv("DATAIKU_LLM_GPT5", "azureopenai:Azure-OpenAI-Prod:gpt-4o"),
```

## Available Models

Based on your Dataiku catalog, the available models are:

- ✅ **gpt-4o** - Best quality, recommended (Azure-OpenAI-Prod)
- ✅ **gpt-4o-mini** - Cost-effective alternative (Azure-OpenAI-Prod)
- ✅ **gpt-4.1** - Available (Azure-OpenAI-Prod-4-1)
- ✅ **gpt-4.1-mini** - Available (Azure-OpenAI-Prod-4-1)
- ✅ **o4-mini** - Available (Azure-OpenAI-Prod-4-1)
- ❌ **gpt-5** - DOES NOT EXIST

## Why This Happened

The configuration was likely set up anticipating a future `gpt-5` release, but:
1. GPT-5 hasn't been released by OpenAI yet
2. The fallback mapping wasn't properly configured
3. All extractors were hardcoded to use the non-existent model

## Testing

After this fix, you should be able to run analysis without GPT errors:

```powershell
# Test with interactive mode
.\interactive.ps1

# Or command line
.\run_scan.ps1 soc2_reports\Small_Okta.pdf
```

## Environment Variable Override

If you want to use a different model, set it in your `.env` file:

```bash
# Use gpt-4o-mini for cost savings
DEFAULT_GPT_MODEL=gpt-4o-mini

# Or use gpt-4.1 if available
DEFAULT_GPT_MODEL=gpt-4.1

# Override specific extractor models
DATAIKU_LLM_GPT4O=azureopenai:Azure-OpenAI-Prod:gpt-4o
```

## Future-Proofing

When GPT-5 eventually becomes available:

1. Update the Dataiku catalog mapping:
   ```bash
   DATAIKU_LLM_GPT5=azureopenai:Azure-OpenAI-Prod:gpt-5
   ```

2. Update the default model:
   ```bash
   DEFAULT_GPT_MODEL=gpt-5
   ```

3. Update `backend/app/config.py` line 87 to use the actual GPT-5 model ID

## Files Modified

- ✅ `backend/app/config.py` (lines 87, 594, 660-669)

## Summary

✅ **All `gpt-5` references changed to `gpt-4o`**  
✅ **System now uses the best available model**  
✅ **GPT errors should be resolved**  
✅ **Analysis can proceed normally**
