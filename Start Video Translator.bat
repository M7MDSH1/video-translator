@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo The app is not set up yet. Double-click Install.bat first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m videotranslator.app %*
