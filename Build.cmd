@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" tools\make_icon.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\prepare_desktop_data.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm desktop-app.spec
if errorlevel 1 goto failed
echo Desktop app built: dist\Royalty Entry\Royalty Entry.exe
exit /b 0
:failed
echo Desktop build failed.
exit /b 1
