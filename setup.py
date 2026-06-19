#!/usr/bin/env python3
"""claudefree Setup — Cross-platform TUI

Run:  python setup.py
      uv run python setup.py      # if using uv

Replaces the legacy setup.sh (Linux/macOS) and setup.cmd (Windows).
"""

from __future__ import annotations

import json
import os
import shutil
import string
import subprocess
import sys
import threading
from getpass import getpass
from pathlib import Path
from typing import NoReturn

# ── Constants ────────────────────────────────────────────────────────────

PROVIDERS_URL = "https://models.dev/api.json"
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
ENV_FILE = SCRIPT_DIR / ".env"

# ── ANSI styling (works on all modern terminals, including Windows 10+) ──

class S:
    RST = "\033[0m"
    BLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GRN = "\033[32m"
    YLW = "\033[33m"
    BLU = "\033[34m"
    MAG = "\033[35m"
    CYN = "\033[36m"

# ── Print helpers ────────────────────────────────────────────────────────

COLS = shutil.get_terminal_size().columns
COLS = min(COLS, 80)


def print_banner() -> None:
    """Render the box-drawn header banner."""
    print(f"{S.CYN}")
    print(f"╔{S.CYN}{'═' * (COLS - 2)}╗")
    print(f"║{S.CYN}{' ' * (COLS - 2)}║")
    line = "✨ claudefree Setup ✨"
    pad = (COLS - 2 - len(line)) // 2
    print(f"║{' ' * pad}{line}{' ' * (COLS - 2 - pad - len(line))}║")
    line = "Free AI for Claude Code — Multi-Provider"
    pad = (COLS - 2 - len(line)) // 2
    print(f"║{' ' * pad}{line}{' ' * (COLS - 2 - pad - len(line))}║")
    print(f"║{''.ljust(COLS - 2)}║")
    print(f"╚{S.CYN}{'═' * (COLS - 2)}╝")
    print(f"{S.RST}")


def print_step(n: int, total: int, desc: str) -> None:
    print(f"\n  {S.BLU}◉{S.RST} {S.BLD}Step {n} of {total}{S.RST}  {desc}")


def _print(sym: str, color: str, msg: str) -> None:
    print(f"  {msg} {color}{sym}{S.RST}")


def ok(msg: str) -> None:
    _print("✓", S.GRN, msg)


def info(msg: str) -> None:
    _print("ℹ", S.CYN, msg)


def warn(msg: str) -> None:
    _print("⚠", S.YLW, msg)


def error(msg: str) -> None:
    _print("✗", S.RED, msg)


def sub(msg: str) -> None:
    """Sub-step in-progress indicator — removed; spinner handles this."""
    pass  # spinner animation replaces the static [..] line


def sub_ok(msg: str) -> None:
    print(f"    {msg} {S.GRN}✓{S.RST}")


def sub_err(msg: str) -> None:
    print(f"    {msg} {S.RED}✗{S.RST}")


def sub_warn(msg: str) -> None:
    print(f"    {msg} {S.YLW}⚠{S.RST}")


def divider() -> None:
    print(f"  {S.DIM}─" * 36)


# ── Spinner ──────────────────────────────────────────────────────────────

_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠏⠎"


class Spinner:
    """Thread-based spinner for long operations."""

    def __init__(self, msg: str = ""):
        self.msg = msg
        self._running = False
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join()
        sys.stdout.write(f"\r    {self.msg} {S.GRN}✓{S.RST}{S.DIM}{S.RST}\n")
        sys.stdout.flush()

    def _spin(self) -> None:
        i = 0
        while self._running:
            ch = _SPINNER_CHARS[i % len(_SPINNER_CHARS)]
            sys.stdout.write(f"\r    {S.CYN}{ch}{S.RST} {self.msg}")
            sys.stdout.flush()
            i += 1
            self._spin_sleep(0.1)

    @staticmethod
    def _spin_sleep(secs: float) -> None:
        """Thread-safe sleep without blocking signals."""
        threading.Event().wait(secs)


# ── Terminal selection helpers ───────────────────────────────────────────

_HAS_FZF = bool(shutil.which("fzf"))
_HAS_FZY = bool(shutil.which("fzy"))

if _HAS_FZF:
    _FUZZY_CMD = "fzf"
elif _HAS_FZY:
    _FUZZY_CMD = "fzy"
else:
    _FUZZY_CMD = None


def _use_fuzzy() -> bool:
    return _FUZZY_CMD is not None and sys.stdin.isatty()


def fuzzy_select(options: list[str], prompt: str = "Search", **kwargs: str) -> str | None:
    """Use fzf/fzy to let the user filter-select from options."""
    if not _use_fuzzy():
        return None
    input_str = "\n".join(options)
    args = [_FUZZY_CMD, "--prompt", f"{prompt}> "]
    for flag, val in kwargs.items():
        args.extend([f"--{flag.replace('_', '-')}", val])
    try:
        result = subprocess.run(
            args, input=input_str, capture_output=True, text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def numbered_menu(options: list[str], prompt: str = "") -> str | None:
    """Fallback numbered menu when fzf/fzy isn't available."""
    for i, opt in enumerate(options, 1):
        print(f"    {S.CYN}{i:3d}{S.RST}) {opt}")
    print()
    label = f"    {prompt} (1-{len(options)}): " if prompt else f"    Enter number (1-{len(options)}): "
    try:
        raw = input(label).strip()
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return None


# ── Shell config detection ───────────────────────────────────────────────

def detect_shell_rc() -> Path | None:
    """Return path to .zshrc or .bashrc, or None."""
    shell = os.environ.get("SHELL", "")
    home = Path.home()
    if "zsh" in shell:
        return home / ".zshrc"
    if "bash" in shell:
        return home / ".bashrc"
    # Windows: no shell rc to modify
    if sys.platform == "win32":
        return None
    return home / ".bashrc"


def is_already_configured(rc: Path | None) -> bool:
    """Check if ANTHROPIC_AUTH_TOKEN is already set in shell rc."""
    if rc is None or not rc.exists():
        return False
    try:
        text = rc.read_text(encoding="utf-8")
        return "ANTHROPIC_AUTH_TOKEN" in text and "God" in text
    except OSError:
        return False


# ── Package manager helpers ──────────────────────────────────────────────

if sys.platform == "win32":
    _HOME_BIN = Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin"
else:
    _HOME_BIN = Path.home() / ".local" / "bin"


def _check_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(*args: str, **kwargs: object) -> bool:
    """Run a command, return True if it succeeded."""
    try:
        subprocess.run(
            args,
            timeout=kwargs.get("timeout", 60),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **{k: v for k, v in kwargs.items() if k in ("shell", "cwd")},
        )
        return True
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return False


def _install_linux(pkg: str) -> bool:
    """Install a package on Linux via the detected package manager."""
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return False
    text = os_release.read_text(encoding="utf-8", errors="replace").lower()
    if "fedora" in text:
        return _run("sudo", "dnf", "install", "-y", pkg)
    if "debian" in text or "ubuntu" in text:
        _run("sudo", "apt-get", "update", "-qq")
        return _run("sudo", "apt-get", "install", "-y", "-qq", pkg)
    if "arch" in text:
        return _run("sudo", "pacman", "-S", pkg, "--noconfirm")
    if "alpine" in text:
        return _run("sudo", "apk", "add", pkg)
    return False


def _install_macos(pkg: str) -> bool:
    return _run("brew", "install", pkg)


def _install_fzy() -> bool:
    """Install fzy fuzzy finder."""
    if _check_cmd("fzy"):
        return True
    sub("Installing fzy via package manager...")
    if sys.platform == "darwin":
        _install_macos("fzy")
    else:
        _install_linux("fzy")
    if _check_cmd("fzy"):
        return True
    # Try git build as fallback
    sub_warn("Package install failed — trying git build...")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ok = _run("git", "clone", "https://github.com/jhawthorn/fzy.git",
                  cwd=tmp, timeout=120)
        if ok:
            _run("make", "-s", cwd=f"{tmp}/fzy", timeout=60)
            _run("sudo", "make", "install", cwd=f"{tmp}/fzy")
    return _check_cmd("fzy")


def _install_fzf() -> bool:
    """Install fzf fuzzy finder (Windows)."""
    if _check_cmd("fzf.exe"):
        return True
    for mgr in ("winget", "scoop", "choco"):
        if _check_cmd(mgr):
            sub(f"Installing fzf via {mgr}...")
            {
                "winget": lambda: _run(mgr, "install", "fzf"),
                "scoop": lambda: _run(mgr, "install", "fzf"),
                "choco": lambda: _run(mgr, "install", "fzf", "-y"),
            }[mgr]()
            if _check_cmd("fzf.exe"):
                return True
    return False


# ── Step implementations ─────────────────────────────────────────────────

def fetch_providers() -> dict | NoReturn:
    """Download and parse the providers JSON."""
    sub("Downloading provider list...")
    spinner = Spinner("Downloading provider list...")
    spinner.start()
    try:
        import urllib.request
        req = urllib.request.Request(PROVIDERS_URL, headers={
            "User-Agent": "claudefree-setup/1.0",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        providers = json.loads(data)
    except Exception as exc:
        spinner.stop()
        sys.stdout.write(f"\r{S.RST}")
        error(f"Failed to fetch providers: {exc}")
        sys.exit(1)
    finally:
        spinner.stop()
    sys.stdout.write(f"\r{S.RST}")
    size_kb = len(data) / 1024
    sub_ok(f"Provider list downloaded ({size_kb:.0f} KB)")
    return providers


def pick_provider(providers: dict) -> str | NoReturn:
    """Let user select a provider."""
    names = sorted(providers.keys())
    choice = fuzzy_select(names, prompt="Provider")
    if choice is None:
        choice = numbered_menu(names, prompt="Enter provider number")
    if not choice:
        error("No provider selected.")
        sys.exit(1)
    ok(f"Selected: {S.BLD}{choice}{S.RST}")
    return choice


def collect_api_key(provider: str) -> str | NoReturn:
    """Get API key from .env or prompt the user."""
    upper = provider.upper().replace("-", "_")
    env_var = f"{upper}_API_KEY"

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith(env_var + "="):
                val = line.split("=", 1)[1].strip().strip("\"'")
                if val:
                    ok("API key found in .env")
                    return val

    print()
    try:
        key = getpass(f"    {S.BLD}Enter API key for {S.CYN}{provider}{S.RST}:\n    {S.DIM}(input hidden){S.RST} ")
    except (EOFError, KeyboardInterrupt):
        error("Cancelled.")
        sys.exit(1)

    if not key.strip():
        error("API key cannot be empty.")
        sys.exit(1)
    ok("API key received")
    return key.strip()


def pick_models(providers: dict, provider: str) -> dict[str, str]:
    """Let user select models for each tier."""
    model_names = sorted(providers[provider]["models"].keys())
    info(f"{len(model_names)} models available")

    def pick_one(tier: str) -> str:
        print()
        print(f"    {S.BLU}── Model for {S.BLD}{tier}{S.RST}{S.BLU} ──{S.RST}")
        print(f"      {S.DIM} 0{S.RST}) [SAME_AS_DEFAULT]")
        print(f"      {S.DIM} 1{S.RST}) [CUSTOM_MODEL]")
        shown = 0
        for name in model_names:
            if shown >= 10:
                break
            print(f"      {S.DIM}{shown + 2:2d}{S.RST}) {name}")
            shown += 1
        if len(model_names) > 10:
            print(f"      {S.DIM}... and {len(model_names) - 10} more available{S.RST}")
        fzf_opts = ["[SAME_AS_DEFAULT]", "[CUSTOM_MODEL]"] + model_names
        choice = fuzzy_select(fzf_opts, prompt=f"Search {tier}")
        if choice == "[CUSTOM_MODEL]":
            return input(f"      {S.BLD}Custom name{S.RST}: ").strip()
        if choice:
            return choice

        # fzf not available — fallback to numbered menu
        try:
            raw = input(f"\n      {S.BLD}Selection{S.RST} (0-{len(model_names) + 1}): ").strip()
            if raw == "0":
                return "[SAME_AS_DEFAULT]"
            if raw == "1":
                return input(f"      {S.BLD}Custom name{S.RST}: ").strip()
            idx = int(raw) - 2
            if 0 <= idx < len(model_names):
                return model_names[idx]
        except (ValueError, EOFError, KeyboardInterrupt):
            pass
        warn("Invalid — using [SAME_AS_DEFAULT]")
        return "[SAME_AS_DEFAULT]"

    models = {
        "DEFAULT": pick_one("DEFAULT"),
        "OPUS": pick_one("OPUS"),
        "SONNET": pick_one("SONNET"),
        "HAIKU": pick_one("HAIKU"),
    }
    divider()
    print(f"    {S.GRN}DEFAULT{S.RST} → {models['DEFAULT']}")
    print(f"    {S.MAG}OPUS{S.RST}    → {models['OPUS']}")
    print(f"    {S.YLW}SONNET{S.RST}   → {models['SONNET']}")
    print(f"    {S.CYN}HAIKU{S.RST}    → {models['HAIKU']}")
    sub_ok("Models configured")
    return models


def save_config(provider: str, api_key: str, models: dict[str, str]) -> None:
    """Write config.json and .env."""
    CONFIG_FILE.write_text(json.dumps({
        "provider": provider,
        "model_default": models["DEFAULT"],
        "model_opus": models["OPUS"],
        "model_sonnet": models["SONNET"],
        "model_haiku": models["HAIKU"],
    }, indent=2) + "\n", encoding="utf-8")

    sub_ok("config.json written")

    env_text = f"# claudefree credentials\n{provider.upper().replace('-', '_')}_API_KEY=\"{api_key}\"\nANTHROPIC_AUTH_TOKEN=\"God\"\n"
    ENV_FILE.write_text(env_text, encoding="utf-8")
    ENV_FILE.chmod(0o600)
    sub_ok(".env written (permissions: 600)")
    info(f"Config:  {S.DIM}{CONFIG_FILE}{S.RST}")
    info(f"Secrets: {S.DIM}{ENV_FILE}{S.RST}")


def setup_shell_env(rc: Path | None, already_configured: bool) -> None:
    """Add ANTHROPIC_* environment variables to shell rc."""
    if already_configured:
        info("Shell environment already configured — skipped")
        return
    if rc is None:
        info("No shell config file found — skipping")
        return

    print()
    info(f"Adding ANTHROPIC vars to {S.BLD}{rc.name}{S.RST}")

    if rc.exists():
        backup = rc.with_suffix(rc.suffix + ".backup")
        shutil.copy2(rc, backup)

    with rc.open("a", encoding="utf-8") as fh:
        fh.write("\n# claudefree Configuration\n")
        fh.write('export ANTHROPIC_AUTH_TOKEN="God"\n')
        fh.write('export ANTHROPIC_BASE_URL="http://localhost:16324"\n')

    sub_ok(f"Added to {rc.name}")
    info(f"Run: {S.BLD}source {rc.name}{S.RST}  (or restart terminal)")


def install_start_server() -> None:
    """Symlink/copy claude-start-server to ~/.local/bin."""
    print()
    info("Installing claude-start-server to PATH...")
    src = SCRIPT_DIR / "claude-start-server"
    _HOME_BIN.mkdir(parents=True, exist_ok=True)
    dest = _HOME_BIN / "claude-start-server"
    if src.exists():
        try:
            if dest.exists():
                dest.unlink()
            dest.symlink_to(src)
            mode = "symlink"
        except (OSError, NotImplementedError):
            shutil.copy2(src, dest)
            mode = "copy"
        sub_ok(f"~/.local/bin/claude-start-server ({mode})")
    else:
        warn("claude-start-server not found in project")


def check_claude_cli() -> None:
    """Check for claude CLI, offer to install if missing."""
    print()
    info("Checking Claude Code CLI...")
    if _check_cmd("claude"):
        ver = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True,
            timeout=10,
        ).stdout.strip() or "installed"
        sub_ok(f"claude CLI found ({ver})")
        return
    warn("claude not found — installing via npm...")
    if _check_cmd("npm"):
        ok = _run("npm", "install", "-g", "@anthropic-ai/claude-code", timeout=120)
        if ok and _check_cmd("claude"):
            sub_ok("claude installed")
        else:
            sub_err("npm install failed")
    else:
        sub_err(f"npm not found. Install Node.js: {S.BLD}https://nodejs.org{S.RST}")


def show_summary(provider: str, models: dict[str, str]) -> None:
    """Render the final summary dashboard."""
    w = COLS - 4
    print(f"\n{S.GRN}")
    print(f"╔{'═' * (COLS - 2)}╗")
    label = "Setup Complete ✓"
    pad = (COLS - 2 - len(label)) // 2
    print(f"║{' ' * pad}{S.BLD}{S.GRN}{label}{S.RST}{S.GRN}{' ' * (COLS - 2 - pad - len(label))}║")
    print(f"╠{'═' * (COLS - 2)}╣")
    for key, val in [("Provider", provider),
                     ("Default Model", models["DEFAULT"]),
                     ("Opus Model", models["OPUS"]),
                     ("Sonnet Model", models["SONNET"]),
                     ("Haiku Model", models["HAIKU"])]:
        print(f"║  {S.BLD}{key:<19}{S.RST}{S.GRN} {val:{w}}{S.RST}{S.GRN}║")
    print(f"╠{'═' * (COLS - 2)}╣")
    print(f"║  {S.DIM}Config  {S.RST}{S.GRN} {CONFIG_FILE!s:{w - 8}}{S.RST}{S.GRN}║")
    print(f"║  {S.DIM}Secrets {S.RST}{S.GRN} {ENV_FILE!s:{w - 8}}{S.RST}{S.GRN}║")
    print(f"╠{'═' * (COLS - 2)}╣")
    print(f"║  {S.BLD}Next Steps:{S.RST}{S.GRN}{' ' * (COLS - 12)}║{S.RST}")
    print(f"║  {S.CYN}1.{S.RST} Start proxy → {S.BLD}claude-start-server{S.RST}{S.GRN}{' ' * 9}║{S.RST}")
    print(f"║  {S.CYN}2.{S.RST} Run Claude  → {S.BLD}claude{S.RST}{S.GRN}{' ' * 14}║{S.RST}")
    print(f"╚{'═' * (COLS - 2)}╝")
    print(f"{S.RST}")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    print_banner()
    # Determine if already configured
    rc = detect_shell_rc()
    already_configured = is_already_configured(rc)

    if already_configured:
        ok("Shell env already configured — skipping environment setup")
    else:
        info("Shell env not configured — will configure at the end")

    TOTAL = 5

    # ── Step 1: Prerequisites ────────────────────────────────────────────
    print_step(1, TOTAL, "Checking prerequisites")
    sub_ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    curl_ok = _check_cmd("curl")
    if curl_ok:
        sub_ok("curl found")
    else:
        sub_warn("curl not found — will use urllib")

    uv_ok = _check_cmd("uv")
    if uv_ok:
        sub_ok("uv found")

    if sys.platform == "win32":
        fzf_installed = _install_fzf()
    else:
        fzy_installed = _install_fzy()

    fuzzy_msg = "fzf ready" if _HAS_FZF else ("fzy ready" if _HAS_FZY else "no fuzzy finder — using numbered menu")
    if _HAS_FZF or _HAS_FZY:
        sub_ok(fuzzy_msg)
    else:
        sub_warn(fuzzy_msg)

    # ── Step 2: Fetch providers ──────────────────────────────────────────
    print_step(2, TOTAL, "Fetching providers from models.dev")
    providers = fetch_providers()

    # ── Step 3: Select provider + API key ────────────────────────────────
    print_step(3, TOTAL, "Select provider and enter API key")
    print()

    provider = pick_provider(providers)
    api_key = collect_api_key(provider)

    # ── Step 4: Select models ────────────────────────────────────────────
    print()
    print_step(4, TOTAL, "Select models per tier")
    models = pick_models(providers, provider)

    # ── Step 5: Save & finalize ──────────────────────────────────────────
    print()
    print_step(5, TOTAL, "Saving configuration")
    save_config(provider, api_key, models)

    setup_shell_env(rc, already_configured)
    install_start_server()
    check_claude_cli()

    # ── Summary ──────────────────────────────────────────────────────────
    show_summary(provider, models)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  Setup cancelled by user {S.YLW}⚠{S.RST}")
        sys.exit(1)
