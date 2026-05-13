@echo off
setlocal enabledelayedexpansion

chcp 65001 >nul

cls
echo ============================================================
echo    claudefree Setup for Windows
echo ============================================================
echo.

where curl >nul 2>&1
if errorlevel 1 (
    echo [ERROR] curl not found. Install curl or use Windows 10+.
    pause
    exit /b 1
)

REM --- Check/Install fzy ---
set "FZY_AVAILABLE=0"
where fzy.exe >nul 2>&1 && set "FZY_AVAILABLE=1"
if "%FZY_AVAILABLE%"=="0" where fzy >nul 2>&1 && set "FZY_AVAILABLE=1"

if "%FZY_AVAILABLE%"=="0" (
    echo [INFO] fzy (fuzzy finder) not found. Installing...
    where winget >nul 2>&1
    if not errorlevel 1 (
        echo        Installing via winget...
        winget install fzy >nul 2>&1
        if not errorlevel 1 set "FZY_AVAILABLE=1"
    )
)
if "%FZY_AVAILABLE%"=="0" (
    where choco >nul 2>&1
    if not errorlevel 1 (
        echo        Installing via Chocolatey...
        choco install fzy -y >nul 2>&1
        if not errorlevel 1 set "FZY_AVAILABLE=1"
    )
)
if "%FZY_AVAILABLE%"=="0" (
    where scoop >nul 2>&1
    if not errorlevel 1 (
        echo        Installing via Scoop...
        scoop install fzy >nul 2>&1
        if not errorlevel 1 set "FZY_AVAILABLE=1"
    )
)
if "%FZY_AVAILABLE%"=="0" (
    echo        [WARN] Could not install fzy automatically.
    echo               Install manually: winget install fzy
    echo               Falling back to numbered menu.
)
echo.

REM --- Detect PowerShell ---
where pwsh >nul 2>&1
if errorlevel 1 (
    set "PS=powershell"
) else (
    set "PS=pwsh"
)

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.json"
set "ENV_FILE=%SCRIPT_DIR%.env"

echo [1/4] Fetching providers from models.dev...
echo.

set "TEMP_API=%TEMP%\claudefree_providers.json"
curl -s https://models.dev/api.json -o "%TEMP_API%" 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to fetch providers from models.dev
    pause
    exit /b 1
)

echo [OK] Providers fetched
echo.

REM --- Provider selection ---
for /f "usebackq delims=" %%A in (`%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.PSObject.Properties.Name | Sort-Object) -join '|'"`) do set "ALL_PROVIDERS=%%A"

echo [2/4] Select a provider:
echo.

if "%FZY_AVAILABLE%"=="1" (
    echo (Using fzy — type to filter, press Enter to select^)
    for /f "usebackq delims=" %%A in (`echo %ALL_PROVIDERS:(^)>=^(% ^| fzy`) do set "SELECTED_PROVIDER=%%A"
) else (
    set "idx=0"
    for %%P in ("%ALL_PROVIDERS:|= "%") do (
        set /a idx+=1
        set "PROVIDER_!idx!=%%~P"
        echo   !idx!. %%~P
    )
    set "PROVIDER_COUNT=%idx%"
    echo.
    :choose_provider
    set /p "PROVIDER_NUM=Enter provider number (1-%PROVIDER_COUNT%): "
    if "!PROVIDER_NUM!"=="" goto choose_provider
    set /a "PROVIDER_NUM=!PROVIDER_NUM!" 2>nul
    if !PROVIDER_NUM! lss 1 goto choose_provider
    if !PROVIDER_NUM! gtr !PROVIDER_COUNT! goto choose_provider
    for %%i in (!PROVIDER_NUM!) do set "SELECTED_PROVIDER=!PROVIDER_%%i!"
)

if "%SELECTED_PROVIDER%"=="" (
    echo [ERROR] No provider selected
    pause
    exit /b 1
)
echo [OK] Selected: %SELECTED_PROVIDER%
echo.

REM --- API key ---
for /f "usebackq delims=" %%A in (`%PS% -NoProfile -Command "('%SELECTED_PROVIDER%'.ToUpper() -replace '-','_')"`) do set "PROVIDER_UPPER=%%A"
set "API_KEY_VAR=%PROVIDER_UPPER%_API_KEY"

echo [3/4] API key for %SELECTED_PROVIDER%:
echo.
set "API_KEY="
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        if "%%A"=="%API_KEY_VAR%" set "API_KEY=%%B"
    )
)
if not "!API_KEY!"=="" (
    echo [OK] API key already found in .env
) else (
    set /p "API_KEY=Enter API key: "
    if "!API_KEY!"=="" (
        echo [ERROR] API key cannot be empty
        pause
        exit /b 1
    )
    echo.
)

REM --- Model selection ---
echo [4/4] Fetching models for %SELECTED_PROVIDER%...
echo.
for /f "usebackq delims=" %%A in (`%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.%SELECTED_PROVIDER%.models.PSObject.Properties.Name | Sort-Object) -join '|'"`) do set "ALL_MODELS=%%A"

if "%ALL_MODELS%"=="" (
    echo [ERROR] No models found for %SELECTED_PROVIDER%
    del "%TEMP_API%"
    pause
    exit /b 1
)
echo [OK] Models fetched
echo.

set "idx=0"
for %%M in ("%ALL_MODELS:|= "%") do (
    set /a idx+=1
    set "MODEL_!idx!=%%~M"
)
set "MODEL_COUNT=%idx%"

call :select_model DEFAULT
set "MODEL_DEFAULT=%MODEL_RESULT%"
call :select_model OPUS
set "MODEL_OPUS=%MODEL_RESULT%"
call :select_model SONNET
set "MODEL_SONNET=%MODEL_RESULT%"
call :select_model HAIKU
set "MODEL_HAIKU=%MODEL_RESULT%"

REM --- Save ---
echo Saving configuration...

if not "%API_KEY%"=="" (
    > "%ENV_FILE%" (
        echo # claudefree credentials
        echo %API_KEY_VAR%=%API_KEY%
        echo ANTHROPIC_AUTH_TOKEN=fr
    )
)

> "%CONFIG_FILE%" (
    echo {
    echo   "provider": "%SELECTED_PROVIDER%",
    echo   "model_default": "%MODEL_DEFAULT%",
    echo   "model_opus": "%MODEL_OPUS%",
    echo   "model_sonnet": "%MODEL_SONNET%",
    echo   "model_haiku": "%MODEL_HAIKU%"
    echo }
)

set "GITIGNORE=%SCRIPT_DIR%.gitignore"
if exist "%GITIGNORE%" (
    findstr /b /c:".env" "%GITIGNORE%" >nul 2>&1
    if errorlevel 1 (
        echo .env>> "%GITIGNORE%"
        echo [INFO] Added .env to .gitignore
    )
) else (
    echo .env> "%GITIGNORE%"
    echo [INFO] Created .gitignore with .env
)

del "%TEMP_API%"

echo.
echo ============================================================
echo   [OK] Setup Complete!
echo ============================================================
echo.
echo  Next steps:
echo.
echo   1. Start the proxy server:
echo      uv run uvicorn server:app --host 0.0.0.0 --port 16324
echo.
echo   2. In another terminal, connect claude:
echo      set ANTHROPIC_BASE_URL=http://localhost:16324
echo      claude
echo.
echo  Configuration: %CONFIG_FILE%
echo  Credentials:   %ENV_FILE%
echo.
pause
exit /b 0

REM ────────────────────────────────────────────────────────────
REM :select_model — fzy or numbered menu for a given tier
REM ────────────────────────────────────────────────────────────
:select_model
set "TIER=%~1"
echo.
echo === Select model for %TIER% tier ===

if "%FZY_AVAILABLE%"=="1" (
    echo (Type to filter, Enter to select^)
    set "FZY_INPUT=[SAME_AS_DEFAULT]" >nul
    for /f "usebackq delims=" %%A in (`(echo [SAME_AS_DEFAULT]^&echo [CUSTOM_MODEL]^&%ALL_MODELS:|=^&echo %) ^| fzy`) do set "MODEL_RESULT=%%A"
    if "!MODEL_RESULT!"=="[CUSTOM_MODEL]" (
        set /p "MODEL_RESULT=Enter custom model name: "
    )
    goto :eof
)

echo   0. [SAME_AS_DEFAULT]
echo   1. [CUSTOM_MODEL]
for /l %%i in (2,1,%MODEL_COUNT%) do (
    if %%i leq 11 (
        set "m=!MODEL_%%i!"
        echo   %%i. !m!
    )
)
if %MODEL_COUNT% gtr 10 (
    set /a "extra=%MODEL_COUNT%-10"
    echo   ... and !extra! more models
)
echo.

:pick_model_%TIER%
set /p "M_NUM=Enter selection for %TIER% (0 or 1 or 2-%MODEL_COUNT%): "
if "!M_NUM!"=="" goto pick_model_%TIER%
set /a "M_NUM=!M_NUM!" 2>nul
if !M_NUM! lss 0 goto pick_model_%TIER%
if !M_NUM! gtr !MODEL_COUNT! goto pick_model_%TIER%

if !M_NUM! equ 0 (
    set "MODEL_RESULT=[SAME_AS_DEFAULT]"
    goto :eof
)
if !M_NUM! equ 1 (
    set /p "MODEL_RESULT=Enter custom model name: "
    goto :eof
)
set /a "MODEL_INDEX=!M_NUM!"
for %%i in (!MODEL_INDEX!) do set "MODEL_RESULT=!MODEL_%%i!"
goto :eof
