# PDF Password Security and Storage

## Critical Information: Password Storage Policy

### ⚠️ Passwords Are NOT Stored

**The PDF password is only used during the initial extraction phase and is NOT persisted.**

### How It Works

```
┌─────────────────┐
│ 1. User Upload  │ → User provides encrypted PDF + password
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Extraction   │ → Password used to decrypt PDF
│    (Temporary)  │ → Text extracted to plain text file
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Storage      │ → DECRYPTED PDF bytes stored in database
│    (Permanent)  │ → Password DISCARDED after use
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. Later Use    │ → Split viewer loads decrypted PDF
│    (No Password)│ → Manual extraction uses decrypted PDF
└─────────────────┘
```

### Where Password Is Used

**✅ Password Required (Upload/Extraction Only):**
- Initial PDF upload
- Text extraction via PyMuPDF (fitz)
- Embedded file extraction
- PDF flattening (if needed)

**✅ No Password Required (After Upload):**
- PDF split/side-by-side viewer
- Manual CUEC extraction
- Manual control extraction  
- Report viewing
- PDF download
- Excel export

### Database Storage

| Column | Content | Encrypted? |
|--------|---------|------------|
| `scans.pdf_file` | Original PDF bytes | ❌ No (decrypted) |
| `scans.embedded_pdf_file` | Embedded PDF bytes | ❌ No (decrypted) |
| `scans.pdf_filename` | Original filename | N/A |
| ~~`scans.password`~~ | **DOES NOT EXIST** | N/A |

### Security Implications

#### ✅ Advantages

1. **No Password Storage Risk**: Passwords can't be leaked from database
2. **Zero Re-authentication**: Users don't re-enter password for viewing
3. **Simplified Access Control**: Only user auth needed, not PDF password
4. **Better UX**: Seamless viewing after upload

#### ⚠️ Trade-offs

1. **Original Encryption Lost**: Stored PDF is decrypted version
2. **Cannot Recover Original**: Password-protected original is gone
3. **Database Access = PDF Access**: Anyone with DB access sees decrypted PDFs

### Password Lifecycle

```python
# Phase 1: Upload
password = request.form.get('password')  # From user input
job['password'] = password  # Temporarily in Redis (expires 24h)

# Phase 2: Extraction  
doc = fitz.open(pdf_path)
if password:
    doc.authenticate(password)  # Decrypts in memory
text = doc.get_text()  # Extract from decrypted version

# Phase 3: Storage
with open(pdf_path, 'rb') as f:
    pdf_bytes = f.read()  # DECRYPTED bytes
scan.pdf_file = pdf_bytes  # Store decrypted in DB
# password is never saved to DB

# Phase 4: Cleanup
os.remove(temp_pdf_path)  # Delete original encrypted file
# Redis job expires after 24h (password gone)
```

### Code Locations

**Password Flow:**
1. [scan_router.py:49](../backend/app/routers/scan_router.py#L49) - Accept password from Form
2. [scan_router.py:97](../backend/app/routers/scan_router.py#L97) - Store in Redis job (temporary)
3. [main.py:895](../backend/app/main.py#L895) - Pass to run_analysis_job
4. [analyze.py:489](../backend/app/analyze.py#L489) - Pass to analyze_pdf_file
5. [pdf_handler.py:273](../backend/app/pdf_handler.py#L273) - Use for decryption
6. **No persistence code** - Password discarded after extraction

**PDF Serving (No Password Needed):**
- [report_router.py:243](../backend/app/routers/report_router.py#L243) - Serve decrypted PDF from `scan.pdf_file`

**Manual Extraction (No Password Needed):**
- [manual_extraction_service.py:208](../backend/app/services/manual_extraction_service.py#L208) - Use decrypted `scan.pdf_file`

### Comparison to Other Approaches

| Approach | Security | Usability | Implementation |
|----------|----------|-----------|----------------|
| **Current: No Storage** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Store encrypted password | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Store original encrypted PDF | ⭐⭐⭐ | ⭐ | ⭐ |
| Re-prompt every time | ⭐⭐⭐ | ⭐ | ⭐⭐ |

### Future Considerations

If password storage becomes required:

1. **Option A: Encrypted Storage**
   ```python
   from cryptography.fernet import Fernet
   key = Fernet.generate_key()  # Store in env var
   f = Fernet(key)
   scan.pdf_password_encrypted = f.encrypt(password.encode())
   ```

2. **Option B: User Keyring**
   - Store password encrypted with user's auth key
   - Decrypt only when user is logged in
   - Better security, worse UX (can't share reports)

3. **Option C: Dual Storage**
   - Store both encrypted original + decrypted copy
   - Allow users to download either version
   - Requires 2x storage space

### FAQ

**Q: What if I need the password later?**  
A: The password is not retrievable. The system stores the decrypted PDF for convenience.

**Q: Is the decrypted PDF secure?**  
A: Yes, it's protected by user authentication and database access controls, just like all other data.

**Q: Can I re-encrypt the PDF after upload?**  
A: No, the original encrypted version is deleted after extraction. You'd need to re-upload.

**Q: What happens if I enter the wrong password?**  
A: Extraction fails immediately with error: "Invalid PDF password - please check your password and try again"

**Q: Does the password appear in logs?**  
A: No, logs show `password='***'` (masked) for security.

**Q: Can I download the password-protected original?**  
A: No, only the decrypted version is stored. Download `/report/{scan_id}/download` for decrypted PDF.

## Best Practices

1. **Clear User Communication**: Inform users that passwords are not stored
2. **Secure Original If Needed**: Users should keep encrypted originals separately
3. **Access Control**: Rely on application auth, not PDF passwords
4. **Audit Logging**: Log password usage attempts (not values)

## Related Documentation

- [PDF_PASSWORD_SUPPORT.md](PDF_PASSWORD_SUPPORT.md) - Implementation details
- [AUTHENTICATION_COMPLETE.md](AUTHENTICATION_COMPLETE.md) - User authentication system
- [AUDIT_TRACKING.md](AUDIT_TRACKING.md) - Audit logging for access control
