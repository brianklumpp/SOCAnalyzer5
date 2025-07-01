# Windows PowerShell script to start both backend (FastAPI) and frontend (React)
# Usage: Right-click and 'Run with PowerShell' or run in a PowerShell terminal

# Start backend (FastAPI)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend/app; python -m uvicorn main:app --reload"

# Start frontend (React)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm start"

Write-Host "Both backend and frontend are starting in new PowerShell windows."
