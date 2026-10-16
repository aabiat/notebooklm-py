#!/usr/bin/env python3
"""Prepare a private single-account deployment; credentials never enter the checkout."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
DEFAULT_STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "notebooklm-chatgpt"


def external_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError("Private state and Google profiles must be outside this repository.")
    return path


def private_write(path: Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="Stable public HTTPS origin, without /mcp")
    parser.add_argument("--profile-dir", required=True, help="Dedicated authenticated Google profile")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    origin = args.origin.rstrip("/")
    url = urlsplit(origin)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.path or url.query or url.fragment):
        parser.error("--origin must be a bare HTTPS origin.")
    try:
        state = external_path(args.state_dir)
        profile = external_path(args.profile_dir)
    except ValueError as exc:
        parser.error(str(exc))
    if not any((profile / name).is_file() for name in ("storage_state.json", "master_token.json")):
        parser.error("Authenticate the dedicated profile with notebooklm login first.")
    if (state / "runtime.env").exists():
        parser.error("runtime.env already exists; refusing to replace credentials.")
    if not sys.stdin.isatty():
        parser.error("Run preparation in an interactive terminal for hidden secret entry.")
    password = getpass.getpass("MCP OAuth password (save in your password manager; >=16 URL-safe characters): ")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,}", password):
        parser.error("Use at least 16 letters, digits, underscores or hyphens for the MCP password.")
    tunnel = getpass.getpass("Cloudflare Tunnel token (hidden): ")
    if not re.fullmatch(r"[A-Za-z0-9._=\-]+", tunnel):
        parser.error("A nonempty Cloudflare Tunnel token is required.")
    os.umask(0o077)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    oauth = state / "oauth"
    oauth.mkdir(exist_ok=True, mode=0o700)
    oauth.chmod(0o700)
    profile.chmod(0o700)
    values = {
        "NOTEBOOKLM_MCP_TOKEN": secrets.token_urlsafe(32),
        "NOTEBOOKLM_MCP_OAUTH_PASSWORD": password,
        "NOTEBOOKLM_MCP_OAUTH_BASE_URL": origin,
        "NOTEBOOKLM_MCP_OAUTH_STATE_PATH": "/data/oauth/chatgpt.json",
        "NOTEBOOKLM_MCP_TRUST_PROXY": "1",
        "NOTEBOOKLM_PROFILE_DIR": str(profile),
        "NOTEBOOKLM_OAUTH_STATE_DIR": str(oauth),
        "NOTEBOOKLM_UID": str(os.getuid()),
        "NOTEBOOKLM_GID": str(os.getgid()),
        "GIT_COMMIT": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "--short=8", "HEAD"], text=True).strip(),
        "CF_TUNNEL_TOKEN": tunnel,
    }
    # Compose dotenv single quotes prevent expansion of $, whitespace and backslashes.
    def quote(value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("Multiline configuration is not supported.")
        return "'" + value.replace("'", "\\'") + "'"
    private_write(state / "runtime.env", "".join(f"{key}={quote(value)}\n" for key, value in values.items()))
    template = Path(__file__).parent / "plugin-template"
    plugin = state / "plugin"
    plugin.mkdir(exist_ok=True, mode=0o700)
    for name in ("plugin.json", "mcp.json"):
        content = (template / name).read_text().replace("https://notebooklm.example.com", origin)
        json.loads(content)
        private_write(plugin / name, content)
    print("Prepared private configuration and a plugin package. No credentials were printed.")
    print(f"MCP endpoint: {origin}/mcp")
    print("Run compose.sh up -d --build on this persistent host.")


if __name__ == "__main__":
    main()
