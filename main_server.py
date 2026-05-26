"""JARVIS headless backend — FastAPI server + voice listener only, no UI window."""

import os
import sys
import threading
import time
import uvicorn

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server import app, start_voice, state


def start_server():
    """Start the FastAPI uvicorn server."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    print("[JARVIS] Starting headless J.A.R.V.I.S. backend on http://127.0.0.1:8000")
    state.add_log("> BOOT > J.A.R.V.I.S. headless systems initializing")

    # 1. Start uvicorn server in a separate thread
    server_thread = threading.Thread(
        target=start_server,
        daemon=True,
        name="jarvis-api",
    )
    server_thread.start()

    # 2. Wait for server boot
    time.sleep(2.0)

    # 3. Initialize voice listening
    try:
        start_voice()
        print("[JARVIS] Voice listener is active. Say 'Hey Jarvis' or issue voice commands.")
    except Exception as e:
        print(f"[JARVIS] Warning: Voice listener could not start: {e}")

    # 4. Block and keep the main process alive
    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[JARVIS] Shutting down headless backend services.")
