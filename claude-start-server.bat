@echo off
setlocal

set "DIR=%~dp0"
uv run --directory "%DIR%" python -m cli.entrypoints %*
