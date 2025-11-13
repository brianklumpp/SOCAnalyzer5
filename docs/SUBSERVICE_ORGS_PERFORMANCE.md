# Subservice Orgs Extractor - Performance Info

## Why It Takes Time

The Subservice Orgs Extractor can take several minutes to complete because:

1. **Multiple Chunks**: The "Description of System" section is split into chunks (typically 10-30 chunks depending on document size)

2. **GPT Calls Per Chunk**: Each chunk requires a GPT API call to extract subservice organizations

3. **Network Latency**: Each API call to Dataiku DSS takes 1-3 seconds

4. **Processing Time**: 
   - 10 chunks = ~20-30 seconds
   - 20 chunks = ~40-60 seconds  
   - 30 chunks = ~60-90 seconds

## Progress Indicators

You should now see:

### In Console:
```
[Subservice Orgs] Processing 15 chunks...
[Subservice Orgs] Chunk 5/15...
```

### In Interactive Mode:
```
⠋ Processing... 00:45 elapsed
```

## What's Happening

The extractor:
1. Loads the Description of System section
2. Splits it into overlapping chunks
3. For each chunk:
   - Sends text to GPT
   - Waits for response
   - Parses JSON results
   - Filters out non-companies
4. Deduplicates and normalizes results
5. Saves to JSON

## If It Seems Stuck

### Check the logs:
```powershell
Get-Content data\logs\subservice_orgs_extractor.log -Tail 20
```

### Look for:
- "Processing chunk X/Y" - Shows progress
- GPT response times in gpt_calls.log
- Any error messages

## Typical Processing Times

| Document Size | Chunks | Time |
|--------------|--------|------|
| Small (50 pages) | 10-15 | 30-45 sec |
| Medium (100 pages) | 15-25 | 45-75 sec |
| Large (200+ pages) | 25-40 | 75-120 sec |

## Tips

1. **Be patient** - The progress indicator shows it's working
2. **Check logs** - If concerned, check the log files
3. **Small documents first** - Test with smaller PDFs first
4. **Network issues** - Slow network to Dataiku will increase time

## If It Actually Hangs

If the counter stops progressing for more than 5 minutes:

1. Press Ctrl+C to stop
2. Check `data\logs\subservice_orgs_extractor.log`
3. Check `data\logs\gpt_calls.log` for stuck API calls
4. Try running a different extractor first
5. Try with a smaller/different PDF

## Configuration

You can adjust chunk size in `.env` (smaller = more chunks = slower):
```
SUBSERVICE_CHUNK_SIZE=1500
```

Lower values are safer but slower. Default is 1500 characters per chunk.
