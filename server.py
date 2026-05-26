"""FastAPI server — Iron Man HUD backend for JARVIS."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

import psutil
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from dotenv import load_dotenv

from agent.loop import run_agent

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
PROFILE_PATH = os.path.join(PROJECT_ROOT, "profile.json")
UI_PATH = os.path.join(PROJECT_ROOT, "ui", "index.html")
START_TIME = time.time()


class HUDState:
    def __init__(self):
        self.system_online = True
        self.jarvis_active = True
        self.mic_status = "standby"  # standby | listening | off
        self.tts_speaking = False
        self.wake_detected = False
        self.api_connected = bool(os.getenv("GROQ_API_KEY"))
        self.processing = False
        self.activity: deque[dict] = deque(maxlen=8)
        self.system_log: deque[str] = deque(maxlen=100)
        self.commands_count = 0
        self.last_response = "Monitoring all systems."
        self.voice_enabled = True
        self._lock = threading.Lock()

    def add_activity(self, label: str, detail: str = "") -> None:
        with self._lock:
            self.activity.appendleft(
                {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "label": label,
                    "detail": detail,
                }
            )

    def add_log(self, line: str) -> None:
        with self._lock:
            self.system_log.appendleft(line)

    def snapshot(self) -> dict[str, Any]:
        battery = psutil.sensors_battery()
        if battery:
            battery_pct = int(battery.percent)
            battery_plugged = battery.power_plugged
        else:
            battery_pct = None
            battery_plugged = True

        net = psutil.net_if_stats()
        net_up = any(s.isup for s in net.values()) if net else False

        with self._lock:
            return {
                "system_online": self.system_online,
                "jarvis_active": self.jarvis_active,
                "mic_status": self.mic_status,
                "tts_speaking": self.tts_speaking,
                "wake_detected": self.wake_detected,
                "api_connected": self.api_connected,
                "processing": self.processing,
                "activity": list(self.activity),
                "system_log": list(self.system_log)[:20],
                "commands_count": self.commands_count,
                "last_response": self.last_response,
                "voice_enabled": self.voice_enabled,
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "ram_percent": psutil.virtual_memory().percent,
                "battery_percent": battery_pct,
                "battery_plugged": battery_plugged,
                "network_up": net_up,
                "uptime_seconds": int(time.time() - START_TIME),
            }


state = HUDState()
ws_clients: set[WebSocket] = set()
_speaker = None
_voice_listener = None


async def broadcast(payload: dict) -> None:
    dead = []
    for ws in list(ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


def _schedule_broadcast(payload: dict) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(payload))
    except RuntimeError:
        pass


def _log_callback(message: str) -> None:
    state.add_activity("PROCESSING", message)
    state.add_log(f"> SYS > {message}")
    _schedule_broadcast({"type": "log", "message": message})
    _schedule_broadcast({"type": "status", "data": state.snapshot()})


def _run_chat(message: str) -> str:
    state.processing = True
    state.add_activity("PROCESSING", "Agent thinking...")
    state.add_log(f"> USER > {message}")
    _schedule_broadcast({"type": "log", "message": f"> USER > {message}"})
    _schedule_broadcast({"type": "status", "data": state.snapshot()})

    response = run_agent(message, _log_callback)
    state.last_response = response
    state.commands_count += 1
    state.processing = False
    state.add_activity("RESPONDING", "Response ready")
    state.add_log(f"> JARVIS > {response[:200]}{'...' if len(response) > 200 else ''}")

    if _speaker:
        state.tts_speaking = True
        _schedule_broadcast({"type": "status", "data": state.snapshot()})

        def speak_done():
            time.sleep(min(len(response) / 12, 30))
            state.tts_speaking = False
            _schedule_broadcast({"type": "status", "data": state.snapshot()})

        _speaker.speak(response[:200])
        threading.Thread(target=speak_done, daemon=True).start()

    _schedule_broadcast({"type": "response", "text": response})
    _schedule_broadcast({"type": "status", "data": state.snapshot()})
    return response


def start_voice() -> None:
    global _speaker, _voice_listener
    from voice.listener import VoiceListener
    from voice.speaker import Speaker

    _speaker = Speaker()

    def on_wake():
        state.wake_detected = True
        state.mic_status = "listening"
        state.add_activity("LISTENING", "Wake word detected")
        state.add_log("> VOICE > Wake word detected")
        _schedule_broadcast({"type": "status", "data": state.snapshot()})
        try:
            import winsound

            winsound.Beep(800, 200)
        except Exception:
            pass
        if _speaker:
            _speaker.speak("Yes?")
        threading.Timer(3.0, _clear_wake_flag).start()

    def _clear_wake_flag():
        state.wake_detected = False
        state.mic_status = "standby" if state.voice_enabled else "off"
        _schedule_broadcast({"type": "status", "data": state.snapshot()})

    def on_command(text: str):
        state.add_activity("PROCESSING", f"Voice: {text[:40]}")
        threading.Thread(target=_run_chat, args=(text,), daemon=True).start()

    def on_error(msg: str):
        state.add_log(f"> ERR > {msg}")
        _schedule_broadcast({"type": "log", "message": msg})

    def on_activity(label: str, detail: str = ""):
        state.add_activity(label, detail)
        _schedule_broadcast({"type": "status", "data": state.snapshot()})

    _voice_listener = VoiceListener(
        wake_word_detected=on_wake,
        command_callback=on_command,
        on_error=on_error,
        on_activity=on_activity,
    )
    if state.voice_enabled:
        ok = _voice_listener.start()
        state.mic_status = "standby" if ok else "off"
        if ok:
            state.add_log("> VOICE > Listener started")


def stop_voice() -> None:
    global _voice_listener
    if _voice_listener:
        _voice_listener.stop()
        _voice_listener = None
    state.mic_status = "off"


app = FastAPI(title="JARVIS HUD Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class VoiceToggleRequest(BaseModel):
    enabled: bool | None = None


@app.get("/")
async def index():
    return FileResponse(UI_PATH)


@app.get("/profile")
async def profile():
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


@app.get("/status")
async def status():
    return state.snapshot()


@app.post("/chat")
async def chat(req: ChatRequest):
    message = (req.message or "").strip()
    if not message:
        return {"response": "", "error": "Empty message"}
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, _run_chat, message)
    return {"response": response}


@app.post("/screenshot")
async def screenshot_endpoint():
    try:
        from vision.screen_agent import understand_screen
        question = "Look at my screen and tell me what you see and what I should do"
        loop = asyncio.get_event_loop()
        description = await loop.run_in_executor(None, understand_screen, question)
        return {"description": description}
    except Exception as e:
        return {"error": f"Screenshot analysis failed: {e}"}



@app.post("/voice/toggle")
async def voice_toggle(req: VoiceToggleRequest | None = None):
    if req and req.enabled is not None:
        state.voice_enabled = req.enabled
    else:
        state.voice_enabled = not state.voice_enabled
    if state.voice_enabled:
        start_voice()
    else:
        stop_voice()
    snap = state.snapshot()
    _schedule_broadcast({"type": "status", "data": snap})
    return snap


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    await ws.send_json({"type": "status", "data": state.snapshot()})
    try:
        while True:
            data = await ws.receive_text()
            if data.strip().lower() == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_clients.discard(ws)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_voice()
    run_server()
