@echo off
cd /d "%~dp0"
python scripts\fetch_calendar.py
start "" http://localhost:8000
python -m http.server 8000
