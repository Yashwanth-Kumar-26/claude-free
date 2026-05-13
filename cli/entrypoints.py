"""CLI entrypoints for claudefree."""

from __future__ import annotations


def serve() -> None:
    """Start the claudefree gateway server."""
    import uvicorn

    from cli.process_registry import kill_all_best_effort
    from settings.env import get_settings

    cfg = get_settings()
    try:
        uvicorn.run(
            "gateway.app:app",
            host=cfg.host,
            port=cfg.port,
            log_level="info",
            timeout_graceful_shutdown=5,
        )
    finally:
        kill_all_best_effort()


def init() -> None:
    """Interactive setup wizard for claudefree."""
    import shutil
    from pathlib import Path

    cfg_dir  = Path.home() / ".config" / "claudefree"
    env_file = cfg_dir / ".env"
    template = Path(__file__).parent.parent / ".env.example"

    cfg_dir.mkdir(parents=True, exist_ok=True)
    if env_file.exists():
        print(f"Config already exists at {env_file}. Edit it manually.")
        return

    if template.exists():
        shutil.copy(template, env_file)
        print(f"Created config at {env_file}")
    else:
        env_file.write_text("# claudefree configuration\nMODEL=nvidia_nim/z-ai/glm4.7\n")
        print(f"Created minimal config at {env_file}")

    print("Edit the file and set your API keys, then run: claude-start-server")


if __name__ == "__main__":
    serve()
