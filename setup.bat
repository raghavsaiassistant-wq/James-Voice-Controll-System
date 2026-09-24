@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Voice Mode setup - sab dependencies check karke jo missing hai wo install karega.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
set ERR=%ERRORLEVEL%
echo.
pause
exit /b %ERR%
