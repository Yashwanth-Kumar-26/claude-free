@echo off
setlocal enabledelayedexpansion
REM ╔═══════════════════════════════════════════════════════════════╗
REM ║  setup.cmd — claudefree Setup                                ║
REM ║                                                              ║
REM ║  Run this in CMD or PowerShell — both work.                   ║
REM ╚═══════════════════════════════════════════════════════════════╝

chcp 65001 >nul 2>&1

REM ── ANSI detection (Windows 10+ build 16257) ──────────────────────────
set "ESC="
for /f %%a in ('echo prompt $E ^| cmd') do if not "%%a"=="$E" set "ESC=%%a"

set "RST="&set "BLD="&set "DIM="&set "RED="&set "GRN="&set "YLW="&set "BLU="&set "CYN="&set "MAG="
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

REM ── Detect PowerShell (prefer pwsh, fallback powershell) ──────────────
set "PS=powershell"
where pwsh >nul 2>&1 && set "PS=pwsh"

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.json"
set "ENV_FILE=%SCRIPT_DIR%.env"
set "TEMP_DIR=%TEMP%\claudefree"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

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
echo.
echo  %BLU%◈%RST% Step %~1 of %~2   %~3
exit /b 0

:ok     echo  %GRN%v%RST% %~1 & exit /b 0
:info   echo  %CYN%i%RST% %~1 & exit /b 0
:warn   echo  %YLW%^>%RST% %~1 & exit /b 0
:fail   echo  %RED%x%RST% %~1 & exit /b 0
:sub    echo    %CYN%.%RST% %~1 & exit /b 0
:sub_ok echo    %GRN%v%RST% %~1 & exit /b 0
:sub_ko echo    %RED%x%RST% %~1 & exit /b 0
:divider echo  %DIM%-----------------------------------%RST% & exit /b 0

:summary
echo.
echo %GRN%╔═══════════════════════════════════════════════════════════════╗%RST%
echo %GRN%║        v Setup Complete                                      ║%RST%
echo %GRN%╠═══════════════════════════════════════════════════════════════╣%RST%
echo %GRN%║  %BLD%Provider      %RST%%GRN% %~1%RST%
echo %GRN%║  %BLD%Default Model %RST%%GRN% %~2%RST%
echo %GRN%║  %BLD%Opus Model    %RST%%GRN% %~3%RST%
echo %GRN%║  %BLD%Sonnet Model  %RST%%GRN% %~4%RST%
echo %GRN%║  %BLD%Haiku Model   %RST%%GRN% %~5%RST%
echo %GRN%╠═══════════════════════════════════════════════════════════════╣%RST%
echo %GRN%║  %DIM%Config  %RST%%GRN% %~6%RST%
echo %GRN%║  %DIM%Secrets %RST%%GRN% %~7%RST%
echo %GRN%╠═══════════════════════════════════════════════════════════════╣%RST%
echo %GRN%║  Close this terminal, open a new one, then:                   ║%RST%
echo %GRN%║    1. claude-start-server                                     ║%RST%
echo %GRN%║    2. In another terminal: claude                             ║%RST%
echo %GRN%╚═══════════════════════════════════════════════════════════════╝%RST%
echo.
exit /b 0

:skip_functions

REM ══════════════════════════════════════════════════════════════════════
REM Script starts here
REM ══════════════════════════════════════════════════════════════════════

call :banner

REM ── Check prerequisites ────────────────────────────────────────────────
call :step "Pre" 8 "Checking prerequisites"

where python >nul 2>&1
if errorlevel 1 (
    call :fail "Python not found — install Python 3.11+ first: https://python.org"
    pause
    exit /b 1
)

REM ── Detect if already configured ────────────────────────────────────────
set "ALREADY_CONFIGURED=0"
if exist "%ENV_FILE%" (
    findstr /b "ANTHROPIC_AUTH_TOKEN=God" "%ENV_FILE%" >nul 2>&1
    if not errorlevel 1 set "ALREADY_CONFIGURED=1"
)
if "%ALREADY_CONFIGURED%"=="1" (
    call :ok "Already configured — skipping environment setup"
) else (
    call :info "Fresh setup — will configure everything"
)

set TOTAL_STEPS=7

REM ══════════════════════════════════════════════════════════════════════
REM Step 1: Install uv (package manager)
REM ══════════════════════════════════════════════════════════════════════
call :step 1 %TOTAL_STEPS% "Installing uv (package manager)"

where uv >nul 2>&1
if not errorlevel 1 goto uv_done

call :sub "Downloading uv installer..."
%PS% -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" >nul 2>&1

REM Refresh PATH — uv installs to %USERPROFILE%\.local\bin
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"

:uv_done
where uv >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%a in ('uv --version 2^>nul') do set "UV_VER=%%a"
    call :sub_ok "uv !UV_VER!"
) else (
    call :warn "uv install failed — will use pip instead"
)

REM ══════════════════════════════════════════════════════════════════════
REM Step 2: Install fzy (fuzzy finder for Windows)
REM ══════════════════════════════════════════════════════════════════════
call :step 2 %TOTAL_STEPS% "Checking fuzzy finder (fzy)"

where fzy >nul 2>&1
if not errorlevel 1 goto fzy_done

call :sub "Installing fzy..."
call :sub "  Trying winget..."
where winget >nul 2>&1 && winget install fzy -e --accept-package-agreements >nul 2>&1

where fzy >nul 2>&1
if errorlevel 1 (
    call :sub "  winget failed — trying choco..."
    where choco >nul 2>&1 && choco install fzy -y >nul 2>&1
)

where fzy >nul 2>&1
if errorlevel 1 (
    call :sub "  choco failed — trying scoop..."
    where scoop >nul 2>&1 && scoop install fzy >nul 2>&1
)

:fzy_done
where fzy >nul 2>&1
if not errorlevel 1 (
    call :sub_ok "fzy ready"
) else (
    call :warn "fzy not available — will use numbered menu instead"
)

REM ══════════════════════════════════════════════════════════════════════
REM Step 3: Install dependencies with uv
REM ══════════════════════════════════════════════════════════════════════
call :step 3 %TOTAL_STEPS% "Installing project dependencies"

if not exist "%SCRIPT_DIR%pyproject.toml" (
    call :warn "No pyproject.toml found — skipping dependency install"
    goto deps_done
)

where uv >nul 2>&1
if not errorlevel 1 (
    call :sub "Running uv sync..."
    cd /d "%SCRIPT_DIR%" 2>nul
    uv sync --frozen >nul 2>&1
    if not errorlevel 1 (
        call :sub_ok "Dependencies installed via uv"
        goto deps_done
    )
    call :warn "uv sync failed — trying pip fallback..."
) else (
    call :sub "uv not available — using pip..."
)

pip install -e "%SCRIPT_DIR%" >nul 2>&1
if not errorlevel 1 (
    call :sub_ok "Dependencies installed via pip"
) else (
    call :warn "pip install failed — you may need to run: pip install -e ."
)

:deps_done

REM ══════════════════════════════════════════════════════════════════════
REM Step 4: Fetch providers
REM ══════════════════════════════════════════════════════════════════════
call :step 4 %TOTAL_STEPS% "Fetching providers from models.dev"

set "TEMP_API=%TEMP_DIR%\providers.json"
call :sub "Downloading provider list..."

%PS% -NoProfile -Command "Invoke-WebRequest -Uri 'https://models.dev/api.json' -OutFile '%TEMP_API%'" >nul 2>&1
if errorlevel 1 (
    %PS% -NoProfile -Command "(New-Object Net.WebClient).DownloadFile('https://models.dev/api.json','%TEMP_API%')" >nul 2>&1
)
if errorlevel 1 (
    call :fail "Failed to fetch providers — check your internet connection"
    pause
    exit /b 1
)
call :sub_ok "Provider list downloaded"
echo.

REM ══════════════════════════════════════════════════════════════════════
REM Step 5: Select provider
REM ══════════════════════════════════════════════════════════════════════
call :step 5 %TOTAL_STEPS% "Select provider"

%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.PSObject.Properties.Name | Sort-Object)" > "%TEMP_DIR%\providers.txt"

echo.
set "FZY_AVAILABLE=0"
where fzy >nul 2>&1 && set "FZY_AVAILABLE=1"

if "%FZY_AVAILABLE%"=="1" (
    echo    %DIM%(Type to filter, Enter to select)%RST%
    type "%TEMP_DIR%\providers.txt" | fzy > "%TEMP_DIR%\selected.txt"
    set /p SELECTED_PROVIDER=<"%TEMP_DIR%\selected.txt" 2>nul
) else (
    set "idx=0"
    for /f "usebackq delims=" %%P in ("%TEMP_DIR%\providers.txt") do (
        set /a idx+=1
        set "PROVIDER_!idx!=%%P"
        echo    %CYN%!idx!%RST%^) %%P
    )
    if !idx! equ 0 (
        call :fail "No providers found"
        pause
        exit /b 1
    )
    set /p "n=    Select (1-!idx!): "
    for %%i in (!n!) do set "SELECTED_PROVIDER=!PROVIDER_%%i!"
)

if not defined SELECTED_PROVIDER (
    call :fail "No provider selected"
    pause
    exit /b 1
)
call :ok "Selected: %BLD%%SELECTED_PROVIDER%%RST%"
echo.

REM ══════════════════════════════════════════════════════════════════════
REM Step 6: Enter API key
REM ══════════════════════════════════════════════════════════════════════
call :step 6 %TOTAL_STEPS% "Enter API key"

%PS% -NoProfile -Command "('%SELECTED_PROVIDER%'.ToUpper() -replace '-','_')" > "%TEMP_DIR%\upper.txt"
set /p PROVIDER_UPPER=<"%TEMP_DIR%\upper.txt"
set "API_KEY_VAR=%PROVIDER_UPPER%_API_KEY"
set "API_KEY="

REM Check if key already exists in .env
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        if /i "%%A"=="%API_KEY_VAR%" set "API_KEY=%%B"
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
REM Step 7: Select models
REM ══════════════════════════════════════════════════════════════════════
call :step 7 %TOTAL_STEPS% "Select models"

%PS% -NoProfile -Command "$j = Get-Content '%TEMP_API%' | ConvertFrom-Json; ($j.%SELECTED_PROVIDER%.models.PSObject.Properties.Name | Sort-Object)" > "%TEMP_DIR%\models.txt"
set /p MODEL_CHECK=<"%TEMP_DIR%\models.txt" 2>nul

if not defined MODEL_CHECK (
    call :fail "No models found for '%SELECTED_PROVIDER%'"
    pause
    exit /b 1
)

set "idx=0"
for /f "usebackq delims=" %%M in ("%TEMP_DIR%\models.txt") do (
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

> "%ENV_FILE%" (
    echo # claudefree credentials
    echo %API_KEY_VAR%=%API_KEY%
    echo ANTHROPIC_AUTH_TOKEN=God
)
call :sub_ok ".env written"

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

REM Cleanup temp files
rmdir /s /q "%TEMP_DIR%" 2>nul

REM ── Shell env vars ──────────────────────────────────────────────────────
echo.
if "%ALREADY_CONFIGURED%"=="0" (
    call :info "Setting ANTHROPIC environment variables..."
    setx ANTHROPIC_AUTH_TOKEN "God" >nul
    setx ANTHROPIC_BASE_URL "http://localhost:16324" >nul
    call :ok "Added to user environment (restart terminal to apply)"
) else (
    call :info "Environment already configured — skipped"
)

REM ── Install claude-start-server ──────────────────────────────────────────
if exist "%SCRIPT_DIR%claude-start-server.bat" (
    mkdir "%USERPROFILE%\.local\bin" 2>nul
    > "%USERPROFILE%\.local\bin\claude-start-server.bat" (
        echo @echo off
        echo set "DIR=%~dp0."
        echo uv run --directory "%%DIR%%" python -m cli.entrypoints %%*
    )
    call :ok "claude-start-server installed to %%USERPROFILE%%\.local\bin"
)

REM ── Check claude CLI ────────────────────────────────────────────────────
echo.
call :info "Checking Claude Code CLI..."
where claude >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%a in ('claude --version 2^>nul') do set "CLAUDE_VER=%%a"
    call :ok "claude CLI found (!CLAUDE_VER!)"
) else (
    call :warn "claude not found — installing via npm..."
    where npm >nul 2>&1 || call :fail "npm not found. Install Node.js: https://nodejs.org"
    if not errorlevel 1 (
        call npm install -g @anthropic-ai/claude-code >nul 2>&1
        where claude >nul 2>&1 && call :ok "claude installed" || call :fail "npm install failed"
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

set /a "maxshow=%MODEL_COUNT%"
if %maxshow% gtr 10 set "maxshow=10"

for /l %%i in (2,1,%maxshow%) do (
    set /a "midx=%%i-1"
    call set "mname=%%MODEL_!midx!%%"
    set "padded=%%i     "
    echo      %DIM%!padded:~0,2!%RST%^) !mname!
)
set /a "extra=%MODEL_COUNT%-%maxshow%"
if %extra% gtr 0 echo      %DIM%... and %extra% more%RST%

if "%FZY_AVAILABLE%"=="1" (
    echo      %DIM%(Type to filter, Enter to select)%RST%
    (
        echo [SAME_AS_DEFAULT]
        echo [CUSTOM_MODEL]
        type "%TEMP_DIR%\models.txt"
    ) > "%TEMP_DIR%\model_list.txt"
    type "%TEMP_DIR%\model_list.txt" | fzy > "%TEMP_DIR%\model_sel.txt"
    set /p MODEL_RESULT=<"%TEMP_DIR%\model_sel.txt" 2>nul
    if "!MODEL_RESULT!"=="[CUSTOM_MODEL]" set /p "MODEL_RESULT=    Custom name: "
) else (
    set /a "MAX_NUM=!MODEL_COUNT!+1"
    set /p "M_NUM=    Selection (0-!MAX_NUM!): "
    if "!M_NUM!"=="0" set "MODEL_RESULT=[SAME_AS_DEFAULT]" & goto model_done
    if "!M_NUM!"=="1" (set /p "MODEL_RESULT=    Custom name: " & goto model_done)
    set /a "midx=!M_NUM!-1"
    call set "MODEL_RESULT=%%MODEL_!midx!%%"
)
:model_done
goto :eof
