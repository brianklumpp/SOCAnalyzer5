# PDF Password Support Implementation

## ⚠️ Important: Password Storage Policy

**Passwords are NOT stored permanently.** The password is only used during the initial PDF extraction and is then discarded. The system stores the **decrypted PDF** in the database for viewing and analysis.

**See [PDF_PASSWORD_SECURITY.md](PDF_PASSWORD_SECURITY.md) for complete details on:**
- How passwords are handled
- Why they're not stored
- Security implications
- PDF storage locations
- Password lifecycle

## Overview
Added comprehensive support for password-protected PDFs throughout the SOC Analyzer application. Users can now upload encrypted PDFs and provide passwords through the UI, which are securely passed through the entire extraction pipeline.

## Changes Made

### Backend Changes

#### 1. PDF Handler (`backend/app/pdf_handler.py`)
- **extract_embedded_files()**: Added optional `password` parameter
  - Opens PDF with password authentication
  - Raises `ValueError` with user-friendly message if password is invalid
  
- **flatten_pdf()**: Added optional `password` parameter
  - Authenticates encrypted PDFs before flattening
  - Raises `ValueError` if authentication fails
  
- **extract_text_from_pdf()**: Added optional `password` parameter
  - Main text extraction function now supports encrypted PDFs
  - Provides clear error messages for invalid passwords

#### 2. Manual Extraction Service (`backend/app/services/manual_extraction_service.py`)
- **extract_text_from_pages()**: Added optional `password` parameter
  - Handles password for stream-based PDF operations
  - Used for manual CUEC/control extraction from specific pages

#### 3. Analysis Pipeline (`backend/app/analyze.py`)
- **analyze_pdf_file()**: Added `password` parameter
  - Threads password through to all PDF processing functions
  - Passes password to extract_embedded_files(), flatten_pdf(), and extract_text_from_pdf()
  - Logs when password is provided (masked in logs)

#### 4. Main Execution (`backend/app/main.py`)
- **run_analysis_job()**: Added `password` parameter
  - Updated function signature to accept password
  - Passes password to analyze_pdf_file()
  - Logs password status (masked)

#### 5. API Endpoints (`backend/app/routers/scan_router.py`)
- **POST /analyze/**: Added optional `password` Form field
  - Single PDF upload now accepts password
  - Stores password in job metadata
  - Passes password to queue and direct execution paths
  
- **POST /analyze/batch**: Added optional `passwords` Form field
  - Batch upload accepts comma-separated list of passwords
  - Each PDF can have its own password
  - Format: "pwd1,,pwd3," (empty strings for no password)

#### 6. Scan Queue (`backend/app/threading/scan_queue.py`)
- **QueuedScan dataclass**: Added `password` field
  - Stores password with scan metadata
  - Persisted in Redis with other scan data
  
- **enqueue()**: Added `password` parameter
  - Queue now tracks password for each scan
  - Worker thread retrieves password when processing

### Frontend Changes

#### 1. Queue Controls (`frontend/src/components/analyzer/QueueControls.tsx`)
- **FileToUpload interface**: Added optional `password` field
- **Password TextField**: Added to each file in batch upload dialog
  - Type="password" for security
  - Placeholder: "Leave blank if no password"
  - Full-width field below priority selector
  
- **handleBatchUpload()**: Updated to send passwords
  - Collects passwords from all files
  - Sends as comma-separated list to backend
  - Empty strings for PDFs without passwords

## Usage

### Single PDF Upload
1. Select PDF file in upload dialog
2. Enter password in "PDF Password (optional)" field
3. Click Upload
4. System will use password for all extraction operations

### Batch PDF Upload
1. Click "Upload PDFs" or drag & drop multiple PDFs
2. For each PDF, optionally enter password in the password field
3. Set report type and priority as usual
4. Click "Upload All"
5. System processes each PDF with its respective password

## Error Handling

### Backend
- All PDF opening functions check for encryption
- `doc.authenticate(password)` validates password
- Raises `ValueError` with message: "Invalid PDF password - please check your password and try again"
- Errors propagate up to user as HTTP 500 with detail message

### Frontend
- Password field type="password" hides input
- Upload errors displayed in Alert component
- Clear error messages guide user to retry with correct password

## Security Considerations

1. **Logging**: Passwords are masked in logs (shown as '***')
2. **Storage**: Passwords stored temporarily in Redis job metadata
3. **Cleanup**: Passwords cleared when job completes/fails
4. **Transmission**: Sent via HTTPS in production
5. **UI**: Password input type="password" prevents shoulder-surfing

## Testing

### Test Scenarios
1. **Unencrypted PDF**: Upload without password - works normally
2. **Encrypted PDF with correct password**: Upload with password - extracts successfully
3. **Encrypted PDF with wrong password**: Upload with wrong password - shows error
4. **Encrypted PDF without password**: Upload without password - shows encryption error
5. **Batch upload mixed**: Some with passwords, some without - all process correctly

### Test Commands
```bash
# Single upload test
curl -X POST http://localhost:8000/analyze/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@encrypted.pdf" \
  -F "password=secretpass"

# Batch upload test
curl -X POST http://localhost:8000/analyze/batch \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@public.pdf" \
  -F "files=@encrypted.pdf" \
  -F "passwords=,secretpass"
```

## Future Enhancements

1. **Password caching**: Remember passwords for previously uploaded PDFs (by hash)
2. **Batch password apply**: Apply same password to multiple files
3. **Certificate-based encryption**: Support for certificate-encrypted PDFs
4. **Password strength indicator**: Show password requirements for PDFs
5. **Keychain integration**: Store passwords securely in system keychain

## Files Modified

### Backend
- `backend/app/pdf_handler.py` - 3 function signatures updated
- `backend/app/services/manual_extraction_service.py` - 1 function updated
- `backend/app/analyze.py` - 1 function signature, 3 function calls updated
- `backend/app/main.py` - 1 function signature, 1 function call updated
- `backend/app/routers/scan_router.py` - 2 endpoints updated
- `backend/app/threading/scan_queue.py` - dataclass and enqueue updated

### Frontend
- `frontend/src/components/analyzer/QueueControls.tsx` - Interface, state, UI, API call updated

## Compatibility

- **PyMuPDF (fitz)**: Supports password parameter natively
- **Existing scans**: Backward compatible - password defaults to None
- **Database**: No schema changes required
- **API**: Backward compatible - password is optional Form field

## Documentation

- Error messages guide users to correct password issues
- Function docstrings updated with password parameter documentation
- Raises clauses added to indicate ValueError on invalid password
