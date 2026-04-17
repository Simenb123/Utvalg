@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m flowchart_editor
) else (
    python -m flowchart_editor
)
