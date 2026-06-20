"""CLI entrypoints for claudefree."""

from __future__ import annotations


def _chdir_project_root() -> None:
    """Change to the project root so config.json/.env are found.

    Checks (in order):
      1. editable-install root — `cli/entrypoints.py` grandparent  (dev setup)
      2. standard user config dir —  ~/.config/claudefree/
      3. current directory already has config — stays put
    """
    import os
    from pathlib import Path

    candidates = [
        Path(__file__).resolve().parent.parent,          # editable install
        Path.home() / ".config" / "claudefree",          # standard user config
    ]
    for root in candidates:
        if root.is_dir() and ((root / "config.json").is_file() or (root / ".env").is_file()):
            os.chdir(root)
            return

    # If CWD already has config, we're fine
    if (Path.cwd() / "config.json").is_file() or (Path.cwd() / ".env").is_file():
        return


def serve() -> None:
    """Start the claudefree gateway server."""
    _chdir_project_root()

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
