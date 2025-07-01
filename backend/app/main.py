
import os
import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from analyze import analyze_pdf_file

app = FastAPI()

# Allow CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "SOCAnalyzer backend is running"}

# Example endpoint for PDF upload (to be connected to analyze.py logic)

# Analyze endpoint: accepts PDF upload, runs analysis, returns results
@app.post("/analyze/")
async def analyze_pdf(file: UploadFile = File(...)):
    # Save uploaded file to a temp location
    temp_dir = "data/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    # Use a fallback filename if file.filename is None
    filename = file.filename if file.filename else "uploaded.pdf"
    temp_pdf_path = os.path.join(temp_dir, filename)
    with open(temp_pdf_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)
    try:
        # Run analysis (calls analyze.py logic)
        results = analyze_pdf_file(temp_pdf_path)
        return JSONResponse({"results": results})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        # Clean up temp file
        try:
            os.remove(temp_pdf_path)
        except Exception:
            pass
