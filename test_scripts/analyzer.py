import argparse
import subprocess
import sys
import os


REDIS_CONTAINER = "socanalyzer-redis"
# --- Use venv python if available ---
def get_python_exe():
    base = os.path.dirname(__file__)
    candidates = [
        os.path.join(base, ".venv", "Scripts", "python.exe"),
        os.path.join(base, "venv", "Scripts", "python.exe"),
        os.path.join(base, "env", "Scripts", "python.exe"),
        "python"
    ]
    for exe in candidates:
        if os.path.exists(exe):
            return exe
    return "python"

PYTHON_EXE = get_python_exe()
BACKEND_CMD = [PYTHON_EXE, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
FRONTEND_CMD = ["npx", "serve", "-s", "build"]

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "backend")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")

backend_proc = None
frontend_proc = None

def start_redis():
    # Check if running
    result = subprocess.run(["docker", "ps", "-q", "--filter", f"name={REDIS_CONTAINER}", "--filter", "status=running"], capture_output=True, text=True)
    if result.stdout.strip():
        print("Redis container already running.")
        return
    # Check if exists
    result = subprocess.run(["docker", "ps", "-a", "-q", "--filter", f"name={REDIS_CONTAINER}"], capture_output=True, text=True)
    if result.stdout.strip():
        print("Redis container exists but is not running. Starting it...")
        subprocess.run(["docker", "start", REDIS_CONTAINER])
        print("Redis container started.")
    else:
        print("Launching new Redis container...")
        subprocess.run(["docker", "run", "-d", "--name", REDIS_CONTAINER, "-p", "6379:6379", "redis"])
        print("Redis container created and started.")

def stop_redis():
    subprocess.run(["docker", "stop", REDIS_CONTAINER])
    print("Redis container stopped.")

def start_backend():
    global backend_proc
    print("Starting backend (FastAPI)...")
    backend_proc = subprocess.Popen(BACKEND_CMD, cwd=BACKEND_DIR)
    print(f"Backend started with PID {backend_proc.pid}.")

def stop_backend():
    # Find and kill uvicorn process
    import signal
    import psutil
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and 'uvicorn' in ' '.join(proc.info['cmdline']):
                print(f"Killing backend process PID {proc.info['pid']}...")
                proc.terminate()
        except Exception:
            pass

def start_frontend():
    global frontend_proc
    print("Starting frontend (React)...")
    # Check if npx and serve are available
    from shutil import which
    if which("npx") is None:
        print("ERROR: 'npx' is not found in your PATH. Please install Node.js and ensure npx is available.")
        sys.exit(1)
    if which("serve") is None:
        print("ERROR: 'serve' is not found in your PATH. Run 'npm install -g serve' to install it globally.")
        sys.exit(1)
    frontend_proc = subprocess.Popen(FRONTEND_CMD, cwd=FRONTEND_DIR)
    print(f"Frontend started with PID {frontend_proc.pid}.")

def stop_frontend():
    # Find and kill serve process
    import signal
    import psutil
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and 'serve' in ' '.join(proc.info['cmdline']):
                print(f"Killing frontend process PID {proc.info['pid']}...")
                proc.terminate()
        except Exception:
            pass

def start_all():
    start_redis()
    start_backend()
    start_frontend()

def stop_all():
    stop_backend()
    stop_frontend()
    stop_redis()

def restart_all():
    stop_all()
    import time
    time.sleep(2)
    start_all()

def main():
    parser = argparse.ArgumentParser(description="SOCAnalyzer service manager")
    parser.add_argument("action", choices=["start", "stop", "restart"], help="Action to perform")
    args = parser.parse_args()
    if args.action == "start":
        start_all()
    elif args.action == "stop":
        stop_all()
    elif args.action == "restart":
        restart_all()

if __name__ == "__main__":
    main()
