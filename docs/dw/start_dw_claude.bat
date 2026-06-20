@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  Desktop-Worker - Elevated Claude Launcher (START / planning)
REM  Repo: C:\Desktop-Worker
REM  Self-elevates via UAC so the CLI broker runs admin-capable.
REM  SAFE FLAGS ONLY - no --dangerously-skip-permissions.
REM ============================================================

REM --- Step 1: ensure admin (self-elevate via UAC) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [dw] Requesting elevation...
    powershell -NoProfile -Command ^
        "Start-Process cmd.exe -ArgumentList '/c \"%~dpnx0\"' -Verb RunAs -Wait"
    exit /b
)

REM --- Step 2: locate claude.exe ---
set CLAUDE_EXE=
for /f "tokens=*" %%i in ('where claude 2^>nul') do (
    if not defined CLAUDE_EXE set CLAUDE_EXE=%%i
)
if not defined CLAUDE_EXE set CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe
if not exist "%CLAUDE_EXE%" (
    echo [dw] ERROR: claude.exe not found. Install Claude Code or fix PATH.
    pause & exit /b 1
)
echo [dw] Claude: %CLAUDE_EXE%

REM --- Step 3: go to repo root ---
set REPO_PATH=C:\Desktop-Worker
cd /d "%REPO_PATH%"
echo [dw] Working dir: %CD%

REM --- Step 4: system prompt ---
set SYSTEM_PROMPT=%REPO_PATH%\docs\dw\dw_claude_system_prompt.md
if not exist "%SYSTEM_PROMPT%" goto :NOPROMPT

echo [dw] Launching (planning mode) with system prompt...
"%CLAUDE_EXE%" --permission-mode plan --append-system-prompt-file "%SYSTEM_PROMPT%"
if %errorlevel% equ 0 goto :EOF
echo [dw] Flag combo not supported; retrying without system-prompt-file...

:NOPROMPT
echo ================================================================
echo  When Claude starts, run:  /ease-me continue
echo  It will read docs\dw\dw_memory.md and dw_state.md
echo ================================================================
"%CLAUDE_EXE%" --permission-mode plan

:EOF
echo [dw] Session ended.
pause
