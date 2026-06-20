@echo off
setlocal

REM ============================================================
REM  Desktop-Worker - Status (no elevation needed)
REM  Prints app status + state file, opens the tracker dashboard.
REM ============================================================

set REPO_PATH=C:\Desktop-Worker
cd /d "%REPO_PATH%"

echo ============================================================
echo  Desktop-Worker status
echo ============================================================
python -m desktop_worker status 2>nul
if %errorlevel% neq 0 (
    echo [dw] Could not run app status. Is Python installed and the package
    echo      installed?  python -m pip install -e ".[dev]"
)

echo.
echo ------------------------------------------------------------
echo  State file: docs\dw\dw_state.md  (Next recommended task)
echo ------------------------------------------------------------
findstr /C:"Next recommended task" /C:"Last completed task" "%REPO_PATH%\docs\dw\dw_state.md"

echo.
echo [dw] Opening tracker dashboard...
start "" "%REPO_PATH%\docs\dw\dw_tracker.html"

pause
