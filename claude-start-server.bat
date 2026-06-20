@echo off
setlocal
cd /d "%~dp0"

REM Use .venv python if available (uv sync creates it), otherwise system python
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cli.entrypoints %*
) else (
    python -m cli.entrypoints %*
)
