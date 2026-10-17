@echo off
setlocal
cd /d "%~dp0"
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" scripts/manage.py %*
  exit /b
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts/manage.py %*
  exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 scripts/manage.py %*
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python scripts/manage.py %*
  exit /b
)
echo Python was not found. Install Python 3.12 or newer and run run-local.cmd setup.
exit /b 1
