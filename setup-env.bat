@echo off
REM setup-env.bat — Configure ANTHROPIC environment variables for Windows

setlocal enabledelayedexpansion

REM Colors (using type command for colored output on Windows 10+)
cls

echo.
echo ===============================================================
echo   ClaudeFree Environment Setup for Windows
echo ===============================================================
echo.

REM Check if running as admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] This script is not running as Administrator
    echo Recommended: Run as Administrator for system-wide configuration
    echo Continuing with current user configuration...
    echo.
    timeout /t 2 >nul
)

REM Check if already configured
setx ANTHROPIC_AUTH_TOKEN >nul 2>&1
if !errorlevel! equ 0 (
    echo [INFO] Checking existing configuration...
    for /f "delims== tokens=2" %%A in ('setx ANTHROPIC_AUTH_TOKEN 2^>nul') do set "EXISTING_TOKEN=%%A"

    if "!EXISTING_TOKEN!"=="God" (
        echo.
        echo [OK] Already configured!
        echo.
        echo Current Configuration:
        echo   ANTHROPIC_AUTH_TOKEN = %ANTHROPIC_AUTH_TOKEN%
        echo   ANTHROPIC_BASE_URL   = %ANTHROPIC_BASE_URL%
        echo.
        pause
        exit /b 0
    )
)

echo [ACTION] Setting up environment variables...
echo.

REM Set environment variables for current user
setx ANTHROPIC_AUTH_TOKEN "God" >nul
if %errorlevel% equ 0 (
    echo [OK] Set: ANTHROPIC_AUTH_TOKEN = God
) else (
    echo ✗ Failed to set ANTHROPIC_AUTH_TOKEN
    pause
    exit /b 1
)

setx ANTHROPIC_BASE_URL "http://localhost:16324" >nul
if %errorlevel% equ 0 (
    echo [OK] Set: ANTHROPIC_BASE_URL = http://localhost:16324
) else (
    echo ✗ Failed to set ANTHROPIC_BASE_URL
    pause
    exit /b 1
)

echo.
echo ===============================================================
echo   [OK] Setup Complete!
echo ===============================================================
echo.

echo Configuration Saved to: User Environment Variables
echo.

echo Next Steps:
echo   1. RESTART your terminal/PowerShell/CMD
echo.
echo   2. Start the server in one terminal:
echo      uv run uvicorn server:app --host 0.0.0.0 --port 16324
echo.
echo   3. In another terminal, just run:
echo      claude
echo.
echo ===============================================================
echo.

echo [INFO] Testing configuration...
timeout /t 2 >nul

REM Show current environment (might be from old session)
echo Current Session Variables:
echo   ANTHROPIC_AUTH_TOKEN = %ANTHROPIC_AUTH_TOKEN%
echo   ANTHROPIC_BASE_URL   = %ANTHROPIC_BASE_URL%
echo.

echo [IMPORTANT] You MUST restart your terminal for changes to take effect!
echo.

pause
