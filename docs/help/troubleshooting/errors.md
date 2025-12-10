# Common Errors

## Extraction Errors

### "Job not found"
**Cause**: Redis connection lost or job expired  
**Solution**:
1. Check Redis container: `docker ps | grep redis`
2. Restart Redis: `docker compose restart redis`
3. Restart scan if needed

### "Failed to extract controls"
**Cause**: PDF format issues, corrupted text extraction  
**Solution**:
1. Verify PDF is not password-protected
2. Try re-uploading the PDF
3. Check PDF text extraction quality
4. Review logs for specific errors

### "Token limit exceeded"
**Cause**: Control section too large for GPT  
**Solution**:
1. Increase token budget in Settings
2. Check for unusually long controls
3. Review chunking parameters
4. Contact support for very large reports

### "No controls detected"
**Cause**: Section detection failed or non-standard format  
**Solution**:
1. Verify PDF contains "Control Descriptions" section
2. Check section detection results
3. Try manual section boundaries
4. Review report structure

## Database Errors

### "Connection refused" (Port 5433)
**Cause**: PostgreSQL container not running  
**Solution**:
```powershell
docker compose up -d postgres
docker compose restart backend
```

### "Duplicate key violation"
**Cause**: Attempting to re-insert existing data  
**Solution**:
1. Delete existing scan first
2. Use unique scan IDs
3. Check for concurrent uploads

### "Foreign key constraint"
**Cause**: Referencing non-existent parent record  
**Solution**:
1. Verify scan exists before inserting controls
2. Check database integrity
3. Review insertion order

## Frontend Errors

### "Failed to load report"
**Cause**: Backend API not responding  
**Solution**:
1. Check backend status: `docker ps`
2. Verify API URL in browser console
3. Restart backend: `docker compose restart backend`
4. Check CORS configuration

### "Network Error"
**Cause**: Frontend can't reach backend  
**Solution**:
1. Verify both containers running
2. Check port 8000 accessible
3. Restart Docker networking: `docker compose down && docker compose up -d`

### "Help pages not loading"
**Cause**: Missing help files or incorrect paths  
**Solution**:
1. Verify help files exist in `docs/help/`
2. Check index.json references
3. Restart backend to reload files

## Upload Errors

### "File too large"
**Cause**: PDF exceeds 25 MB limit  
**Solution**:
1. Compress PDF if possible
2. Split large reports
3. Contact admin to increase limit

### "Invalid file type"
**Cause**: Uploaded file is not a PDF  
**Solution**:
1. Verify file extension is .pdf
2. Check file isn't corrupted
3. Try saving PDF again from source

### "Upload timeout"
**Cause**: Network slow or file too large  
**Solution**:
1. Check network connection
2. Try smaller file
3. Increase timeout in settings

## Docker Errors

### "Container not found"
**Cause**: Container stopped or removed  
**Solution**:
```powershell
docker compose up -d
```

### "Port already in use"
**Cause**: Another service using port 8000 or 3000  
**Solution**:
1. Stop conflicting service
2. Change port in docker-compose.yml
3. Use different port mapping

### "Volume mount failed"
**Cause**: Path doesn't exist or permissions issue  
**Solution**:
1. Verify local paths exist
2. Check Docker Desktop settings
3. Run Docker as administrator

## GPT API Errors

### "Rate limit exceeded"
**Cause**: Too many API calls  
**Solution**:
1. Wait and retry
2. Check API quotas
3. Reduce concurrent scans

### "API key invalid"
**Cause**: Incorrect or expired API key  
**Solution**:
1. Verify API key in .env file
2. Check key has OpenAI access
3. Regenerate key if needed

### "Model not found"
**Cause**: Requesting unavailable model  
**Solution**:
1. Use GPT-4 or GPT-3.5-turbo
2. Check model availability
3. Update model selection in Settings

## Quick Diagnostics

### Check All Services
```powershell
docker compose ps
```

### View Backend Logs
```powershell
docker compose logs backend --tail 50
```

### View Frontend Logs
```powershell
docker compose logs frontend --tail 50
```

### Restart Everything
```powershell
docker compose restart
```

### Nuclear Option (Fresh Start)
```powershell
docker compose down
docker compose up -d
```
