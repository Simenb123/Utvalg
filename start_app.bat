@echo off
setlocal

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Fant ikke virtuelt miljo i .venv
  echo Opprett det forst, eller gi beskjed sa setter vi det opp.
  pause
  exit /b 1
)

"%PYTHON_EXE%" "%~dp0main.py"
