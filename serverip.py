"""
claudefree — IP Address Exposure Utility

Exposes the ClaudeFree server on local network IP address.
Displays connection details for remote access.

Usage:
    python serverip.py
"""

import socket

from settings.env import get_settings


def get_local_ip():
    """Get local IP address visible on network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_hostname():
    """Get system hostname."""
    try:
        return socket.gethostname()
    except Exception:
        return "localhost"


def display_connection_info():
    """Display server connection information."""
    cfg = get_settings()
    local_ip = get_local_ip()
    hostname = get_hostname()

    print("\n" + "=" * 70)
    print("  ClaudeFree Server - IP Address Exposure")
    print("=" * 70 + "\n")

    print("Local Connection:")
    print(f"  URL: http://localhost:{cfg.port}")
    print(f"  Command: ANTHROPIC_BASE_URL=http://localhost:{cfg.port} claude\n")

    if local_ip != "127.0.0.1":
        print("Network Connection (same LAN):")
        print(f"  IP Address: {local_ip}")
        print(f"  URL: http://{local_ip}:{cfg.port}")
        print(f"  Hostname: {hostname}")
        print(f"  Command: ANTHROPIC_BASE_URL=http://{local_ip}:{cfg.port} claude\n")

        print("For Remote Access:")
        print(f"  1. Ensure firewall allows port {cfg.port}")
        print(f"  2. Share IP: {local_ip}:{cfg.port} with remote user")
        print(f"  3. Remote runs: ANTHROPIC_BASE_URL=http://{local_ip}:{cfg.port} claude\n")

    print("Authentication:")
    print("  Token: ANTHROPIC_AUTH_TOKEN=God (pre-configured)\n")

    print("=" * 70 + "\n")


if __name__ == "__main__":
    display_connection_info()
