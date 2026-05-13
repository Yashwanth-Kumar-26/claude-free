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
        winget install fzy >nul 2>&1
        if not errorlevel 1 set "FZY_AVAILABLE=1"
    )
)
if "%FZY_AVAILABLE%"=="0" (
    where choco >nul 2>&1
    if not errorlevel 1 (
        choco install fzy -y >nul 2>&1
        if not errorlevel 1 set "FZY_AVAILABLE=1"
    )
)
if "%FZY_AVAILABLE%"=="0" (
    where scoop >nul 2>&1
    if not errorlevel 1 (
        scoop install fzy >nul 2>&1
        if not errorlevel 1 set "FZY_AVAILABLE=1"
    )
)
if "%FZY_AVAILABLE%"=="0" (
    echo [WARN] Could not install fzy automatically.
    echo        Falling back to numbered menu.
)
echo.

REM --- Detect PowerShell ---
where pwsh >nul 2>&1
if errorlevel 1 (set "PS=powershell") else (set "PS=pwsh")

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.json"
set "ENV_FILE=%SCRIPT_DIR%.env"

REM ────────────────────────────────────────────────────────────
REM Step 1: Fetch providers
REM ────────────────────────────────────────────────────────────
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

REM ────────────────────────────────────────────────────────────
REM Step 2: Select provider
REM ────────────────────────────────────────────────────────────
%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.PSObject.Properties.Name | Sort-Object) -join '|'" > "%TEMP%\cf_providers.txt"
set /p ALL_PROVIDERS=<"%TEMP%\cf_providers.txt"

echo [2/4] Select a provider:
echo.
if "%FZY_AVAILABLE%"=="1" goto fzy_provider
goto menu_provider

:fzy_provider
echo (Type to filter, press Enter to select^)
%PS% -NoProfile -Command "$data = Get-Content '%TEMP%\cf_providers.txt' -Raw; $data -split '\|' | fzy" > "%TEMP%\cf_selected.txt"
set /p SELECTED_PROVIDER=<"%TEMP%\cf_selected.txt"
if "%SELECTED_PROVIDER%"=="" (
    echo [ERROR] No provider selected
    del "%TEMP%\cf_providers.txt" "%TEMP%\cf_selected.txt" 2>nul
    pause
    exit /b 1
)
goto provider_done

:menu_provider
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
if "%PROVIDER_NUM%"=="" goto choose_provider
set /a "PROVIDER_NUM=%PROVIDER_NUM%" 2>nul
if %PROVIDER_NUM% lss 1 goto choose_provider
if %PROVIDER_NUM% gtr %PROVIDER_COUNT% goto choose_provider
for %%i in (%PROVIDER_NUM%) do set "SELECTED_PROVIDER=!PROVIDER_%%i!"

:provider_done
echo [OK] Selected: %SELECTED_PROVIDER%
echo.

REM ────────────────────────────────────────────────────────────
REM Step 3: API key
REM ────────────────────────────────────────────────────────────
%PS% -NoProfile -Command "('%SELECTED_PROVIDER%'.ToUpper() -replace '-','_')" > "%TEMP%\cf_upper.txt"
set /p PROVIDER_UPPER=<"%TEMP%\cf_upper.txt"
set "API_KEY_VAR=%PROVIDER_UPPER%_API_KEY"

echo [3/4] API key for %SELECTED_PROVIDER%:
echo.
set "API_KEY="
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        if "%%A"=="%API_KEY_VAR%" set "API_KEY=%%B"
    )
)
if not "%API_KEY%"=="" (
    echo [OK] API key already found in .env
) else (
    set /p "API_KEY=Enter API key: "
    if "%API_KEY%"=="" (
        echo [ERROR] API key cannot be empty
        pause
        exit /b 1
    )
    echo.
)

REM ────────────────────────────────────────────────────────────
REM Step 4: Select models per tier
REM ────────────────────────────────────────────────────────────
echo [4/4] Fetching models for %SELECTED_PROVIDER%...
echo.
%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.%SELECTED_PROVIDER%.models.PSObject.Properties.Name | Sort-Object) -join '|'" > "%TEMP%\cf_models.txt"
set /p ALL_MODELS=<"%TEMP%\cf_models.txt"

if "%ALL_MODELS%"=="" (
    echo [ERROR] No models found for %SELECTED_PROVIDER%
    del "%TEMP_API%" "%TEMP%\cf_*.txt" 2>nul
    pause
    exit /b 1
)
echo [OK] Models fetched
echo.

REM Build model array
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

REM ────────────────────────────────────────────────────────────
REM Step 5: Save configuration
REM ────────────────────────────────────────────────────────────
echo Saving configuration...

if not "%API_KEY%"=="" (
    > "%ENV_FILE%" (
        echo # claudefree credentials
        echo %API_KEY_VAR%=%API_KEY%
        echo ANTHROPIC_AUTH_TOKEN=God
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

if exist "%SCRIPT_DIR%.gitignore" (
    findstr /b /c:".env" "%SCRIPT_DIR%.gitignore" >nul 2>&1
    if errorlevel 1 (
        echo .env>> "%SCRIPT_DIR%.gitignore"
        echo [INFO] Added .env to .gitignore
    )
) else (
    echo .env> "%SCRIPT_DIR%.gitignore"
    echo [INFO] Created .gitignore with .env
)

del "%TEMP_API%" "%TEMP%\cf_*.txt" 2>nul

REM Install claude-start-server.bat to PATH
copy /y "%SCRIPT_DIR%claude-start-server.bat" "%USERPROFILE%\.local\bin\" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Could not install to %%USERPROFILE%%\.local\bin
    echo        Add "%SCRIPT_DIR%" to your PATH or run claude-start-server from the project folder.
)

echo.
echo ============================================================
echo   [OK] Setup Complete!
echo ============================================================
echo.
echo  Next steps:
echo.
echo   1. Start the proxy server:
echo      claude-start-server
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
if "%FZY_AVAILABLE%"=="1" goto fzy_model_%TIER%
goto menu_model_%TIER%

:fzy_model_%TIER%
echo (Type to filter, Enter to select^)
(
  echo [SAME_AS_DEFAULT]
  echo [CUSTOM_MODEL]
  %ALL_MODELS:|=^
  echo %
) > "%TEMP%\cf_model_list_%TIER%.txt"
type "%TEMP%\cf_model_list_%TIER%.txt" | fzy > "%TEMP%\cf_model_sel_%TIER%.txt"
set /p MODEL_RESULT=<"%TEMP%\cf_model_sel_%TIER%.txt"
if "%MODEL_RESULT%"=="[CUSTOM_MODEL]" (
    set /p "MODEL_RESULT=Enter custom model name: "
)
del "%TEMP%\cf_model_list_%TIER%.txt" "%TEMP%\cf_model_sel_%TIER%.txt" 2>nul
goto :eof

:menu_model_%TIER%
echo   0. [SAME_AS_DEFAULT]
echo   1. [CUSTOM_MODEL]
for /l %%i in (2,1,%MODEL_COUNT%) do (
    if %%i leq 11 (
        echo   %%i. !MODEL_%%i!
    )
)
if %MODEL_COUNT% gtr 10 (
    set /a "extra=%MODEL_COUNT%-10"
    echo   ... and !extra! more models
)
echo.
:pick_model_%TIER%
set /p "M_NUM=Enter selection for %TIER% (0 or 1 or 2-%MODEL_COUNT%): "
if "%M_NUM%"=="" goto pick_model_%TIER%
set /a "M_NUM=%M_NUM%" 2>nul
if %M_NUM% lss 0 goto pick_model_%TIER%
if %M_NUM% gtr %MODEL_COUNT% goto pick_model_%TIER%
if %M_NUM% equ 0 set "MODEL_RESULT=[SAME_AS_DEFAULT]"&goto :eof
if %M_NUM% equ 1 (
    set /p "MODEL_RESULT=Enter custom model name: "
    goto :eof
)
for %%i in (%M_NUM%) do set "MODEL_RESULT=!MODEL_%%i!"
goto :eof
