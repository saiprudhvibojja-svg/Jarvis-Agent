"""JARVIS HUD Entrypoint — Starts backend and opens Chrome app mode UI."""

import os
import sys
import threading
import time
import subprocess
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server import app, start_voice, state, run_server


def start_backend():
    """Start the FastAPI uvicorn server in a separate background thread."""
    print("[JARVIS] Launching backend server on port 8000...")
    run_server(host="127.0.0.1", port=8000)


def launch_chrome_app():
    """Attempt to launch Chrome in application mode. Fall back to standard browser open."""
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    
    app_url = "http://localhost:8000"
    opened = False

    print("[JARVIS] Launching interface...")
    for path in chrome_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path, f"--app={app_url}"])
                opened = True
                print(f"[JARVIS] Interface loaded in Chrome App mode from {path}")
                break
            except Exception as e:
                print(f"[JARVIS] Failed to open Chrome via path {path}: {e}")

    if not opened:
        print("[JARVIS] Chrome application not found. Opening in default browser.")
        webbrowser.open(app_url)


if __name__ == "__main__":
    print("[JARVIS] Initializing systems...")
    state.add_log("> BOOT > J.A.R.V.I.S. systems initializing")

    # 1. Start the backend FastAPI server in a background thread
    server_thread = threading.Thread(
        target=start_backend,
        daemon=True,
        name="jarvis-server"
    )
    server_thread.start()

    # 2. Wait for server to bind port
    time.sleep(2.0)

    # 3. Start the voice interface
    try:
        start_voice()
        print("[JARVIS] Voice recognition interface ready.")
    except Exception as e:
        print(f"[JARVIS] Warning: Voice listener could not start: {e}")

    # 4. Open Chrome app mode interface
    launch_chrome_app()

    # 5. Keep parent thread active
    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[JARVIS] Shutting down J.A.R.V.I.S. launcher.")
