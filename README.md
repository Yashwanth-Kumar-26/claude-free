# claudefree: Universal Provider Proxy

Anthropic-compatible gateway routing Claude Code to 115+ LLM backends — including OpenCode Go/Zen.

## Quick Start

### 1. Initial Setup (One-time)

**Step 1A:** Configure backend models:
```bash
./setup.sh
```

This sets up:
- Backend providers (OpenRouter, NVIDIA NIM, OpenCode)
- Model configuration
- API keys from environment

**Step 1B:** Configure environment variables:

**Linux/macOS:**
```bash
bash setup-env.sh
```

**Windows:**
```cmd
setup-env.bat
```

This sets:
```
ANTHROPIC_AUTH_TOKEN=God
ANTHROPIC_BASE_URL=http://localhost:16324
```

See [SETUP_ENV.md](SETUP_ENV.md) for detailed instructions.

### 2. Start Server

**Option A: Using claudefree command (Recommended - After setup.sh)**
```bash
claudefree
```
Automatically starts the ClaudeFree server on port 16324 using your configured backend.

**Option B: Using Claude Serve**
```bash
claude serve
```
Integrates with Claude Code's native serve command.

**Option C: Using uv/uvicorn directly**
```bash
uv run uvicorn server:app --host 0.0.0.0 --port 16324
```

**Option D: Using Python directly**
```bash
python server.py
```

### 3. Connect Claude Client

After running setup-env.sh or setup-env.bat, simply:

```bash
claude
```

Or manually (without setup):
```bash
ANTHROPIC_AUTH_TOKEN="God" ANTHROPIC_BASE_URL="http://localhost:16324" claude
```

### 4. Network Exposure (Optional)

To expose the server on your local network IP for remote access:

```bash
python serverip.py
```

This displays:
- Local connection URL (localhost:16324)
- Network IP address for same-LAN access
- Hostname connection options
- Instructions for firewall configuration

---

## Configuration

### Backend Selection
Edit `.env` or config.json to choose backend:
```bash
DEFAULT_BACKEND_ID=open_router  # or nvidia_nim
OPENROUTER_API_KEY=sk-...
```

### Supported Backends
- OpenRouter (native Anthropic protocol)
- NVIDIA NIM (OpenAI-compatible)
- OpenCode (dynamic multi-transport)

### Environment Variables

| Variable | Default | Required |
|----------|---------|----------|
| ANTHROPIC_AUTH_TOKEN | God | No |
| ANTHROPIC_BASE_URL | http://localhost:16324 | No |
| OPENROUTER_API_KEY | - | Yes (for OpenRouter) |
| NVIDIA_NIM_API_KEY | - | Yes (for NVIDIA NIM) |
| PORT | 16324 | No |
| HOST | 0.0.0.0 | No |

---

## Architecture

ClaudeFree routes requests through:
1. FastAPI Gateway (auth, shortcuts, model selection)
2. Backend Adapter (format conversion)
3. Transport Layer (HTTP streaming)
4. External API (provider endpoint)
5. SSE Response (Anthropic format back to client)

See [Arch.md](Arch.md) for detailed architecture.

---

## Development

### Install Dependencies
```bash
uv sync
```

### Run Tests
```bash
pytest tests/
```

### Run with Logging
```bash
uv run uvicorn server:app --host 0.0.0.0 --port 16324 --log-level debug
```

### Test Providers
```bash
python -m cli.test_providers
```

---

## Environment Setup

For persistent environment configuration across sessions:

- **Linux/macOS:** See [SETUP_ENV.md](SETUP_ENV.md)
- **Windows:** See [SETUP_ENV.md](SETUP_ENV.md)

This allows you to run `claude` directly without typing environment variables.

---

## Troubleshooting

### Gateway not starting?
- Check port 16324 is available
- Verify Python 3.11+
- Check .env file exists

### Authentication fails?
- Verify ANTHROPIC_AUTH_TOKEN environment variable is set
- Check OPENROUTER_API_KEY or NVIDIA_NIM_API_KEY

### Model routing issues?
- Check DEFAULT_BACKEND_ID is valid
- Verify backend API keys in .env

See [Arch.md](Arch.md) for request flow debugging.

---

## Files

- `setup.sh` - Backend configuration
- `setup-env.sh` - Linux/macOS environment setup
- `setup-env.bat` - Windows environment setup
- `serverip.py` - Network IP exposure and connection info
- `Arch.md` - Architecture documentation
- `SETUP_ENV.md` - Environment setup guide
