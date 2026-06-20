@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  Desktop-Worker - Elevated Claude Launcher (CONTINUE)
REM  Resumes the most recent conversation in the repo.
REM  SAFE FLAGS ONLY.
REM ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [dw] Requesting elevation...
    powershell -NoProfile -Command ^
        "Start-Process cmd.exe -ArgumentList '/c \"%~dpnx0\"' -Verb RunAs -Wait"
    exit /b
)

set CLAUDE_EXE=
for /f "tokens=*" %%i in ('where claude 2^>nul') do (
    if not defined CLAUDE_EXE set CLAUDE_EXE=%%i
)
if not defined CLAUDE_EXE set CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe
if not exist "%CLAUDE_EXE%" (
    echo [dw] ERROR: claude.exe not found.
    pause & exit /b 1
)

set REPO_PATH=C:\Desktop-Worker
cd /d "%REPO_PATH%"
set SYSTEM_PROMPT=%REPO_PATH%\docs\dw\dw_claude_system_prompt.md

echo [dw] Continuing most recent conversation...
if exist "%SYSTEM_PROMPT%" (
    "%CLAUDE_EXE%" --continue --append-system-prompt-file "%SYSTEM_PROMPT%"
    if %errorlevel% equ 0 goto :EOF
)
echo [dw] Falling back to plain --continue. Run /ease-me continue inside Claude.
"%CLAUDE_EXE%" --continue

:EOF
echo [dw] Session ended.
pause
