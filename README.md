# claudefree: Universal Provider Proxy

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi)
![uv](https://img.shields.io/badge/uv-Package_Manager-purple?style=for-the-badge)

![Linux](https://img.shields.io/badge/Linux-Supported-black?style=for-the-badge&logo=linux)
![Windows](https://img.shields.io/badge/Windows-Compatible-0078D6?style=for-the-badge&logo=windows)
![Repo Size](https://img.shields.io/github/repo-size/Yashwanth-Kumar-26/claude-free?style=for-the-badge)
![Visitors](https://visitor-badge.laobi.icu/badge?page_id=Yashwanth-Kumar-26.claude-free)

</div>

---

**claudefree** is an Anthropic-compatible gateway that routes Claude Code to **115+ LLM backends**, powered by dynamic provider discovery from [models.dev](https://github.com/anomalyco/models.dev).

---

## Quick Start

Run the single **cross-platform** setup — works on Linux, macOS, and Windows:

```bash
git clone https://github.com/Yashwanth-Kumar-26/claude-free.git
cd claude-free
python setup.py
```

The setup handles everything

Then start the proxy and Claude in separate terminals:

```bash
claude-start-server   # terminal 1
claude                # terminal 2 | in your project
```

Verify with `/status` inside Claude Code CLI.
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
A single proxy that speaks Anthropic-compatible API on one side, and can route to OpenRouter, NVIDIA NIM, Groq, Mistral, DeepSeek, Ollama cloud, and 107+ others on the other side.

**One gateway. 115+ providers. Zero hardcoding.**

>  **If you find claudefree useful, please give it a star ⭐ !** It helps the project grow and lets others discover it.

---

## Configuration

### Backend Selection
Edit `config.json` or re-run `python setup.py` to change:
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
| `setup.py` | **Cross-platform** |
| `claude-start-server` | Start script (bash) |
| `claude-start-server.bat` | Start script (Windows) |
| `config.json` | Provider and model configuration |
| `.env` | API keys and secrets |
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
# Install dependencies (uv is preferred)
uv sync                # or: pip install -e .
pytest tests/          # Run tests
claude-start-server    # Start with logging
```

## Contributing

Contributions and issues are welcome! If you'd like to contribute, feel free to open a PR or report an issue.

---

<div align="center">
  Made with ❤️ by <a href="https://github.com/Yashwanth-Kumar-26">Yashwanth-Kumar-26</a> & <a href="https://github.com/saiadarsh-03">saiadarsh-03</a>
</div>
