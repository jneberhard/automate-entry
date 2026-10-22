@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Open Start.cmd to launch Royalty Entry.
pause
exit /b 0
:failed
echo Setup failed. Python 3.11 or newer and an internet connection are required.
pause
exit /b 1
