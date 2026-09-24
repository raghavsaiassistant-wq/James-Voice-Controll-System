@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Voice Mode abhi install nahi hua. Pehle setup.bat chalao.
  pause
  exit /b 1
)
title Voice Mode
".venv\Scripts\python.exe" -m voicemode %*
if errorlevel 1 pause
