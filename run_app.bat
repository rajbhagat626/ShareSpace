@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
echo Starting ShareSpace...
echo Open your browser to: http://127.0.0.1:5000
.\venv\Scripts\python.exe app.py
pause
