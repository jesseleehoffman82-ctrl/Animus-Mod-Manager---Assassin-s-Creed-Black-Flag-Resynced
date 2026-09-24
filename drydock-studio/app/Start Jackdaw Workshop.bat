@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0JackdawWorkshop3D.ps1"
if errorlevel 1 pause
