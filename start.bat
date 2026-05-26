@echo off
cd C:\Jarvis-agent
call venv\Scripts\activate
start "" cmd /c "python main_server.py"
timeout /t 2
npx electron .
