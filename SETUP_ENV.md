# ClaudeFree Environment Setup Guide

Quick setup scripts to configure ANTHROPIC_AUTH_TOKEN and ANTHROPIC_BASE_URL environment variables.

## Linux and macOS

### Quick Setup
```bash
bash setup-env.sh
```

**What it does:**
- Detects your shell (bash/zsh)
- Adds environment variables to ~/.bashrc or ~/.zshrc
- Sources the configuration immediately
- Creates a backup of your shell config

**After setup:**
```bash
# Just run
claude
```

---

## Windows 10/11

### Quick Setup
```cmd
setup-env.bat
```

**What it does:**
- Sets environment variables via setx command
- Saves to User Environment Variables
- Shows current configuration

**Important:** After running, RESTART your terminal/PowerShell for changes to take effect.

**After setup:**
```cmd
claude
```

---

## Manual Setup (if scripts don't work)

### Linux/macOS
Add to ~/.bashrc or ~/.zshrc:
```bash
export ANTHROPIC_AUTH_TOKEN="God"
export ANTHROPIC_BASE_URL="http://localhost:16324"
```

Then:
```bash
source ~/.bashrc  # or ~/.zshrc
```

### Windows (PowerShell)
```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_AUTH_TOKEN", "God", "User")
[Environment]::SetEnvironmentVariable("ANTHROPIC_BASE_URL", "http://localhost:16324", "User")
```

---

## Verify Setup

### Linux/macOS
```bash
echo $ANTHROPIC_AUTH_TOKEN
echo $ANTHROPIC_BASE_URL
```

### Windows (PowerShell)
```powershell
$env:ANTHROPIC_AUTH_TOKEN
$env:ANTHROPIC_BASE_URL
```

### Windows (CMD)
```cmd
echo %ANTHROPIC_AUTH_TOKEN%
echo %ANTHROPIC_BASE_URL%
```

---

## Usage

**Terminal 1 - Start server (after setup.sh):**
```bash
claude-start-server
```

Or manually with uvicorn:
```bash
uv run uvicorn server:app --host 0.0.0.0 --port 16324
```

**Terminal 2 - Run Claude:**
```bash
claude
```

**Optional - Check Network IP:**
```bash
python serverip.py
```

This shows your local IP address and connection instructions for remote access on the same network.

That's it! After setup, just run `claude-start-server` to start the server and `claude` to connect.

---

## Troubleshooting

### Variables not working?
- Linux/macOS: Run source ~/.bashrc or restart terminal
- Windows: Restart terminal/PowerShell completely

### Permission denied on Linux/macOS?
```bash
chmod +x setup-env.sh
./setup-env.sh
```

### Can't run .bat on Windows?
- Right-click Run as Administrator
- Or use PowerShell: .\setup-env.bat

---

## Location of Environment Files

| OS | File |
|---|---|
| Linux | ~/.bashrc |
| macOS | ~/.zshrc or ~/.bash_profile |
| Windows | User Environment Variables (Settings) |


