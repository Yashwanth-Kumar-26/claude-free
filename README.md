# claudefree: Universal Provider Proxy

Anthropic-compatible gateway routing Claude Code to 115+ LLM backends — fetched from [models.dev](https://github.com/anomalyco/models.dev.git).


## Quick Start

### 1. Setup

**Linux / macOS:**
```bash
git clone https://github.com/Yashwanth-Kumar-26/claude-free
cd claude-free
./setup.sh
```

**Windows:**
```cmd
git clone https://github.com/Yashwanth-Kumar-26/claude-free
cd claude-free
.\setup.cmd
```

This guides you through:
- Selecting a provider (OpenRouter, NVIDIA NIM, OpenCode, etc.)
- Picking models for each tier (default/opus/sonnet/haiku)
- Entering API keys
- Setting `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` env vars (first run only)

### 2. Start Server

```bash
claude-start-server
```

Or directly with python:
```bash
python server.py
```

### 3. Connect Claude

```bash
claude
```
### 4. Network Exposure (Optional)

```bash
python serverip.py
```

---

## Why claudefree?

### The Problem
Claude Code CLI is powerful, but it's bound to Anthropic's API. Using Claude with other providers (OpenRouter, NVIDIA NIM, Groq, Ollama, etc.) requires building custom routing logic — and most people build it wrong.

### The Discovery
While researching Claude Code integration, I found OpenRouter's [cookbook guide](https://openrouter.ai/docs/cookbook/coding-agents/claude-code-integration) showing a simple pattern: **set a base URL and Claude routes to any Anthropic-compatible provider**. 

But then I discovered something better: **[models.dev](https://github.com/anomalyco/models.dev)** — an open-source catalog of 115+ LLM providers and their capabilities, maintained by the community.

### The Insight
Instead of hardcoding backends one-by-one, why not leverage a dynamic provider registry? This single decision became claudefree's core: 
- **Discover providers dynamically** (no code changes needed for new ones)
- **Route intelligently** (select by cost, latency, capability)
- **Eliminate vendor lock-in** (seamlessly swap providers)

### What You Get
A single proxy that speaks Anthropic-compatible API on one side, and can route to OpenRouter, NVIDIA NIM, Groq, Mistral, DeepSeek, Ollama cloud ,, and 107+ others on the other side.

**One gateway. 115+ providers. Zero hardcoding.**


>  **If you find claudefree useful, please give it a star ⭐ !** It helps the project grow and lets others discover it.
---

## Configuration

### Backend Selection
Edit `config.json` or re-run `setup.sh`/`setup.cmd` to change:
```json
{
  "provider": "open_router",
  "model_default": "...",
  "model_opus": "...",
  "model_sonnet": "...",
  "model_haiku": "..."
}
```

### Supported Backends
- OpenRouter (native Anthropic protocol)
- NVIDIA NIM (OpenAI-compatible)
- OpenCode (dynamic multi-transport)
- Any provider from [models.dev](https://github.com/anomalyco/models.dev.git)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_AUTH_TOKEN` | God | Auth token for Claude client |
| `ANTHROPIC_BASE_URL` | http://localhost:16324 | Proxy URL for Claude |
| `{PROVIDER}_API_KEY` | - | Your provider API key |
| `PORT` | 16324 | Server port |
| `HOST` | 0.0.0.0 | Bind address |

---

## Files

| File | Purpose |
|------|---------|
| `setup.sh` | Full setup for Linux/macOS |
| `setup.cmd` | Full setup for Windows |
| `claude-start-server` | Start script (bash) |
| `claude-start-server.bat` | Start script (Windows) |
| `config.json` | Provider and model configuration |
| `.env` | API keys and secrets |
| `serverip.py` | Network IP exposure utility |
| `Arch.md` | Architecture documentation |

---

## Architecture

ClaudeFree routes requests through:
1. FastAPI Gateway (auth, shortcuts, model selection)
2. Backend Adapter (format conversion)
3. Transport Layer (HTTP streaming)
4. External API (provider endpoint)
5. SSE Response (Anthropic format back to client)

## Development

```bash
uv sync              # Install dependencies
pytest tests/        # Run tests
claude-start-server  # Start with logging
```
