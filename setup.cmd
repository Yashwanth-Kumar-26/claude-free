@echo off
setlocal enabledelayedexpansion
REM ╔═══════════════════════════════════════════════════════════════╗
REM ║  setup.cmd — claudefree Setup (DEPRECATED)                   ║
REM ║                                                              ║
REM ║  ⚠ This script is deprecated. Use the cross-platform         ║
REM ║    setup.py instead:  python setup.py                        ║
REM ╚═══════════════════════════════════════════════════════════════╝

chcp 65001 >nul

REM ── ANSI detection (Windows 10+ build 16257) ──────────────────────────
set "ESC="
for /f %%a in ('echo prompt $E ^| cmd') do if not "%%a"=="$E" set "ESC=%%a"

set "RST="
set "BLD="
set "DIM="
set "RED="
set "GRN="
set "YLW="
set "BLU="
set "CYN="
set "MAG="
if defined ESC (
    set "RST=%ESC%[0m"
    set "BLD=%ESC%[1m"
    set "DIM=%ESC%[2m"
    set "RED=%ESC%[0;31m"
    set "GRN=%ESC%[0;32m"
    set "YLW=%ESC%[1;33m"
    set "BLU=%ESC%[0;34m"
    set "CYN=%ESC%[0;36m"
    set "MAG=%ESC%[0;35m"
)

REM ── Detect PowerShell ──────────────────────────────────────────────────
where pwsh >nul 2>&1
if errorlevel 1 (set "PS=powershell") else (set "PS=pwsh")

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.json"
set "ENV_FILE=%SCRIPT_DIR%.env"

REM ── Print helpers ──────────────────────────────────────────────────────
goto :skip_functions

:banner
cls
echo.
echo %CYN%╔═══════════════════════════════════════════════════════════════╗%RST%
echo %CYN%║                                                              ║%RST%
echo %CYN%║            . claudefree Setup .                               ║%RST%
echo %CYN%║    Free AI for Claude Code - Multi-Provider                   ║%RST%
echo %CYN%║                                                              ║%RST%
echo %CYN%╚═══════════════════════════════════════════════════════════════╝%RST%
echo.
exit /b 0

:step
set "STEP_NUM=%~1"
set "STEP_TOTAL=%~2"
set "STEP_DESC=%~3"
echo.
echo  %BLU%◈%RST% Step %STEP_NUM% of %STEP_TOTAL%   %STEP_DESC%
exit /b 0

:ok
echo  %GRN%v%RST% %~1
exit /b 0

:info
echo  %CYN%i%RST% %~1
exit /b 0

:warn
echo  %YLW%^>%RST% %~1
exit /b 0

:fail
echo  %RED%x%RST% %~1
exit /b 0

:sub
echo    %CYN%.%RST% %~1
exit /b 0

:sub_ok
echo    %GRN%v%RST% %~1
exit /b 0

:sub_ko
echo    %RED%x%RST% %~1
exit /b 0

:divider
echo  %DIM%-----------------------------------%RST%
exit /b 0

:summary
set "S_PROVIDER=%~1"
set "S_DEFAULT=%~2"
set "S_OPUS=%~3"
set "S_SONNET=%~4"
set "S_HAIKU=%~5"
set "S_CONFIG=%~6"
set "S_SECRETS=%~7"
echo.
echo %GRN%╔═══════════════════════════════════════════════════════════════╗%RST%
echo %GRN%║        v Setup Complete                                      ║%RST%
echo %GRN%╠═══════════════════════════════════════════════════════════════╣%RST%
echo %GRN%║  %BLD%Provider         %RST%%GRN% %S_PROVIDER%                                               ║%RST%
echo %GRN%║  %BLD%Default Model    %RST%%GRN% %S_DEFAULT%                                              ║%RST%
echo %GRN%║  %BLD%Opus Model       %RST%%GRN% %S_OPUS%                                                 ║%RST%
echo %GRN%║  %BLD%Sonnet Model     %RST%%GRN% %S_SONNET%                                               ║%RST%
echo %GRN%║  %BLD%Haiku Model      %RST%%GRN% %S_HAIKU%                                                ║%RST%
echo %GRN%╠═══════════════════════════════════════════════════════════════╣%RST%
echo %GRN%║  %DIM%Config   %RST%%GRN% %S_CONFIG%  ║%RST%
echo %GRN%║  %DIM%Secrets  %RST%%GRN% %S_SECRETS%  ║%RST%
echo %GRN%╠═══════════════════════════════════════════════════════════════╣%RST%
echo %GRN%║  Next Steps:                                                 ║%RST%
echo %GRN%║    1. Start proxy - claude-start-server                       ║%RST%
echo %GRN%║    2. Run Claude  - claude                                    ║%RST%
echo %GRN%╚═══════════════════════════════════════════════════════════════╝%RST%
echo.
exit /b 0

:skip_functions

REM ══════════════════════════════════════════════════════════════════════
REM Script starts here
REM ══════════════════════════════════════════════════════════════════════

call :banner

REM ── Detect if already configured ────────────────────────────────────────
set "ALREADY_CONFIGURED=0"
if exist "%ENV_FILE%" (
    findstr /b "ANTHROPIC_AUTH_TOKEN=God" "%ENV_FILE%" >nul 2>&1
    if not errorlevel 1 set "ALREADY_CONFIGURED=1"
)
if "%ALREADY_CONFIGURED%"=="1" (
    call :ok "Shell env already configured - skipping environment setup"
) else (
    call :info "Shell env not configured - will configure at the end"
)

set TOTAL_STEPS=4

REM ══════════════════════════════════════════════════════════════════════
REM Step 1: Fetch providers
REM ══════════════════════════════════════════════════════════════════════
call :step 1 %TOTAL_STEPS% "Fetching providers from models.dev"

set "TEMP_API=%TEMP%\claudefree_providers.json"
call :sub "Downloading provider list..."
%PS% -NoProfile -Command "Invoke-WebRequest -Uri 'https://models.dev/api.json' -OutFile '%TEMP_API%'" >nul 2>&1
if errorlevel 1 (
    %PS% -NoProfile -Command "(New-Object Net.WebClient).DownloadFile('https://models.dev/api.json','%TEMP_API%')" >nul 2>&1
)
if errorlevel 1 (
    call :fail "Failed to fetch providers - check your internet connection"
    pause
    exit /b 1
)
call :sub_ok "Provider list downloaded"
echo.

REM ══════════════════════════════════════════════════════════════════════
REM Step 2: Select provider
REM ══════════════════════════════════════════════════════════════════════
call :step 2 %TOTAL_STEPS% "Select provider"

REM Extract provider names
%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.PSObject.Properties.Name | Sort-Object)" > "%TEMP%\cf_providers.txt"

echo.
set "FZF_AVAILABLE=0"
where fzf.exe >nul 2>&1
if not errorlevel 1 set "FZF_AVAILABLE=1"

if "%FZF_AVAILABLE%"=="1" (
    echo    %DIM%(Type to filter, Enter to select)%RST%
    type "%TEMP%\cf_providers.txt" | fzf.exe > "%TEMP%\cf_selected.txt"
    set /p SELECTED_PROVIDER=<"%TEMP%\cf_selected.txt" 2>nul
) else (
    set "idx=0"
    for /f "usebackq delims=" %%P in ("%TEMP%\cf_providers.txt") do (
        set /a idx+=1
        set "PROVIDER_!idx!=%%P"
        echo    %CYN%!idx!%RST%^) %%P
    )
    set "PROVIDER_COUNT=!idx!"
    echo.
    set /p "n=    Select (1-!PROVIDER_COUNT!): "
    for %%i in (!n!) do set "SELECTED_PROVIDER=!PROVIDER_%%i!"
)

if not defined SELECTED_PROVIDER (
    call :fail "No provider selected"
    del "%TEMP%\cf_providers.txt" "%TEMP%\cf_selected.txt" 2>nul
    pause
    exit /b 1
)
call :ok "Selected: %BLD%%SELECTED_PROVIDER%%RST%"
echo.

REM ══════════════════════════════════════════════════════════════════════
REM Step 3: Enter API key
REM ══════════════════════════════════════════════════════════════════════
call :step 3 %TOTAL_STEPS% "Enter API key"

REM Get uppercase provider name
%PS% -NoProfile -Command "('%SELECTED_PROVIDER%'.ToUpper() -replace '-','_')" > "%TEMP%\cf_upper.txt"
set /p PROVIDER_UPPER=<"%TEMP%\cf_upper.txt"
set "API_KEY_VAR=%PROVIDER_UPPER%_API_KEY"
set "API_KEY="

if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        if "%%A"=="%API_KEY_VAR%" set "API_KEY=%%B"
    )
)
if defined API_KEY (
    call :ok "API key found in .env"
) else (
    echo.
    set /p "API_KEY=    API key for %SELECTED_PROVIDER%: "
    if "!API_KEY!"=="" (
        call :fail "API key cannot be empty"
        pause
        exit /b 1
    )
    call :ok "API key received"
)
echo.

REM ══════════════════════════════════════════════════════════════════════
REM Step 4: Select models
REM ══════════════════════════════════════════════════════════════════════
call :step 4 %TOTAL_STEPS% "Select models"

%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.%SELECTED_PROVIDER%.models.PSObject.Properties.Name | Sort-Object)" > "%TEMP%\cf_models.txt"
for /f "usebackq delims=" %%M in ("%TEMP%\cf_models.txt") do set "MODEL_CHECK=%%M"

if not defined MODEL_CHECK (
    call :fail "No models found for '%SELECTED_PROVIDER%'"
    del "%TEMP_API%" "%TEMP%\cf_*.txt" 2>nul
    pause
    exit /b 1
)

set "idx=0"
for /f "usebackq delims=" %%M in ("%TEMP%\cf_models.txt") do (
    set /a idx+=1
    set "MODEL_!idx!=%%M"
)
set "MODEL_COUNT=!idx!"
call :info "%MODEL_COUNT% models available"
echo.

call :select_model "DEFAULT"
set "MODEL_DEFAULT=%MODEL_RESULT%"
call :select_model "OPUS"
set "MODEL_OPUS=%MODEL_RESULT%"
call :select_model "SONNET"
set "MODEL_SONNET=%MODEL_RESULT%"
call :select_model "HAIKU"
set "MODEL_HAIKU=%MODEL_RESULT%"

call :divider
echo    %GRN%DEFAULT%RST% -^> %MODEL_DEFAULT%
echo    %MAG%OPUS%RST%    -^> %MODEL_OPUS%
echo    %YLW%SONNET%RST%   -^> %MODEL_SONNET%
echo    %CYN%HAIKU%RST%    -^> %MODEL_HAIKU%
call :sub_ok "Models configured"
echo.

REM ══════════════════════════════════════════════════════════════════════
REM Save configuration
REM ══════════════════════════════════════════════════════════════════════
echo Saving configuration...

REM Write .env
> "%ENV_FILE%" (
    echo # claudefree credentials
    echo %API_KEY_VAR%=%API_KEY%
    echo ANTHROPIC_AUTH_TOKEN=God
)
call :sub_ok ".env written"

REM Write config.json
> "%CONFIG_FILE%" (
    echo {
    echo   "provider": "%SELECTED_PROVIDER%",
    echo   "model_default": "%MODEL_DEFAULT%",
    echo   "model_opus": "%MODEL_OPUS%",
    echo   "model_sonnet": "%MODEL_SONNET%",
    echo   "model_haiku": "%MODEL_HAIKU%"
    echo }
)
call :sub_ok "config.json written"

REM Ensure .env is in .gitignore
if exist "%SCRIPT_DIR%.gitignore" (
    findstr /b /c:".env" "%SCRIPT_DIR%.gitignore" >nul 2>&1
    if errorlevel 1 (echo .env>> "%SCRIPT_DIR%.gitignore")
) else (
    echo .env> "%SCRIPT_DIR%.gitignore"
)

del "%TEMP_API%" "%TEMP%\cf_*.txt" 2>nul

REM ── Shell env vars ──────────────────────────────────────────────────────
echo.
if "%ALREADY_CONFIGURED%"=="0" (
    call :info "Setting ANTHROPIC environment variables..."
    setx ANTHROPIC_AUTH_TOKEN "God" >nul
    setx ANTHROPIC_BASE_URL "http://localhost:16324" >nul
    call :ok "Added to user environment. Restart your terminal."
) else (
    call :info "Environment already configured - skipped"
)

REM ── Install claude-start-server ─────────────────────────────────────────
if exist "%SCRIPT_DIR%claude-start-server.bat" (
    mkdir "%USERPROFILE%\.local\bin" 2>nul
    > "%USERPROFILE%\.local\bin\claude-start-server.bat" (
        echo @echo off
        echo setlocal
        echo set "DIR=%SCRIPT_DIR:~0,-1%"
        echo uv run --directory "%%DIR%%" python -m cli.entrypoints %%*
    )
    if not errorlevel 1 (
        call :ok "Installed to %%USERPROFILE%%\.local\bin"
    ) else (
        call :info "Add %SCRIPT_DIR% to your PATH"
    )
)

REM ── Check claude CLI ────────────────────────────────────────────────────
echo.
call :info "Checking Claude Code CLI..."
where claude >nul 2>&1
if not errorlevel 1 (
    call :ok "claude CLI found"
) else (
    call :warn "claude not found - installing via npm..."
    where npm >nul 2>&1
    if not errorlevel 1 (
        call npm install -g @anthropic-ai/claude-code >nul 2>&1
        where claude >nul 2>&1
        if not errorlevel 1 (
            call :ok "claude installed"
        ) else (
            call :fail "npm install failed"
        )
    ) else (
        call :fail "npm not found. Install Node.js first: https://nodejs.org"
    )
)

REM ── Final summary ───────────────────────────────────────────────────────
call :summary "%SELECTED_PROVIDER%" "%MODEL_DEFAULT%" "%MODEL_OPUS%" "%MODEL_SONNET%" "%MODEL_HAIKU%" "%CONFIG_FILE%" "%ENV_FILE%"

pause
exit /b 0

REM ══════════════════════════════════════════════════════════════════════
REM :select_model
REM ══════════════════════════════════════════════════════════════════════
:select_model
set "TIER=%~1"
echo.
echo    %BLU%-- Model for %TIER% --%RST%
echo      %DIM%0%RST%^) [SAME_AS_DEFAULT]
echo      %DIM%1%RST%^) [CUSTOM_MODEL]

set "shown=0"
set "maxshow=10"
if %MODEL_COUNT% lss %maxshow% set /a "maxshow=%MODEL_COUNT%"
for /l %%i in (2,1,%maxshow%) do (
    set /a "midx=%%i-1"
    call set "mname=%%MODEL_!midx!%%"
    set "padded=%%i     "
    echo      %DIM%!padded:~0,2!%RST%^) !mname!
)
set /a "extra=%MODEL_COUNT%-%maxshow%"
if %extra% gtr 0 (
    if %MODEL_COUNT% gtr 10 (
        echo      %DIM%... and %extra% more models available%RST%
    )
)

if "%FZF_AVAILABLE%"=="1" (
    echo      %DIM%(Type to filter, Enter to select)%RST%
    (
        echo [SAME_AS_DEFAULT]
        echo [CUSTOM_MODEL]
        type "%TEMP%\cf_models.txt"
    ) > "%TEMP%\cf_model_list.txt"
    type "%TEMP%\cf_model_list.txt" | fzf.exe > "%TEMP%\cf_model_sel.txt"
    set /p MODEL_RESULT=<"%TEMP%\cf_model_sel.txt" 2>nul
    if "!MODEL_RESULT!"=="[CUSTOM_MODEL]" (
        set /p "MODEL_RESULT=    Custom name: "
    )
    del "%TEMP%\cf_model_list.txt" "%TEMP%\cf_model_sel.txt" 2>nul
) else (
    echo.
    set /a "MAX_NUM=!MODEL_COUNT!+1"
    set /p "M_NUM=    Selection (0-!MAX_NUM!): "
    if "!M_NUM!"=="0" set "MODEL_RESULT=[SAME_AS_DEFAULT]" & goto model_done
    if "!M_NUM!"=="1" (
        set /p "MODEL_RESULT=    Custom name: "
        goto model_done
    )
    set /a "midx=!M_NUM!-1"
    call set "MODEL_RESULT=%%MODEL_!midx!%%"
)
:model_done
goto :eof
