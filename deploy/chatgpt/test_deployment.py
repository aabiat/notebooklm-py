"""Security checks for the additive deployment preparation (no Google requests)."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
from dotenv import dotenv_values

SPEC = importlib.util.spec_from_file_location("chatgpt_prepare", Path(__file__).with_name("prepare.py"))
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def test_private_configuration_and_plugin(tmp_path, monkeypatch, capsys):
    profile = tmp_path / "google" / "personal"
    profile.mkdir(parents=True)
    (profile / "storage_state.json").write_text('{}')
    state = tmp_path / "runtime"
    password = "fake-test-password-12345"
    tunnel = "fake-tunnel-token"
    answers = iter((password, tunnel))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(prepare.getpass, "getpass", lambda _: next(answers))
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--origin", "https://test.example.com",
                                     "--profile-dir", str(profile), "--state-dir", str(state)])
    previous_umask = os.umask(0o022)
    try:
        prepare.main()
    finally:
        os.umask(previous_umask)
    output = capsys.readouterr().out
    assert password not in output and tunnel not in output
    values = dotenv_values(state / "runtime.env")
    assert values["NOTEBOOKLM_MCP_OAUTH_PASSWORD"] == password
    assert values["CF_TUNNEL_TOKEN"] == tunnel
    assert values["NOTEBOOKLM_PROFILE_DIR"] == str(profile)
    assert len(values["NOTEBOOKLM_MCP_TOKEN"]) >= 32
    assert (state.stat().st_mode & 0o777) == 0o700
    assert ((state / "oauth").stat().st_mode & 0o777) == 0o700
    assert ((state / "runtime.env").stat().st_mode & 0o777) == 0o600
    mcp_text = (state / "plugin/mcp.json").read_text()
    assert password not in mcp_text and tunnel not in mcp_text
    entry = json.loads(mcp_text)["mcpServers"]["notebooklm"]
    assert entry["url"] == "https://test.example.com/mcp"
    assert entry["type"] == "streamable-http"
    assert "headers" not in entry
    original = (state / "runtime.env").read_bytes()
    with pytest.raises(SystemExit):
        prepare.main()
    assert (state / "runtime.env").read_bytes() == original


def test_reject_state_inside_repository():
    with pytest.raises(ValueError, match="outside"):
        prepare.external_path(prepare.REPO / "private-state")


def test_secret_file_creation_does_not_follow_symlinks(tmp_path):
    target = tmp_path / "target"
    target.write_text("preserve")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        prepare.private_write(link, "replacement")
    assert target.read_text() == "preserve"


@pytest.mark.asyncio
async def test_real_http_transport_with_simulated_google(monkeypatch, tmp_path):
    import argparse
    import asyncio
    from contextlib import asynccontextmanager
    from dataclasses import dataclass
    import secrets
    import socket
    from unittest.mock import AsyncMock, MagicMock

    import uvicorn
    from notebooklm.mcp._auth import build_auth
    from notebooklm.mcp._oauth import SelfHostedOAuthProvider
    from notebooklm.mcp.server import create_server
    from notebooklm.types import Notebook

    smoke_spec = importlib.util.spec_from_file_location("chatgpt_smoke", Path(__file__).with_name("verify_mcp.py"))
    smoke = importlib.util.module_from_spec(smoke_spec)
    smoke_spec.loader.exec_module(smoke)

    @dataclass
    class Answer:
        answer: str = "Simulated NotebookLM response"
        conversation_id: str = "test-conversation"
        turn_number: int = 1
        references: tuple = ()

    notebook_id = "11111111-1111-1111-1111-111111111111"
    google = MagicMock()
    google.notebooks.list = AsyncMock(return_value=[Notebook(id=notebook_id, title="Simulated", sources_count=1, is_owner=True)])
    google.chat.ask = AsyncMock(return_value=Answer())
    google.chat.get_conversation_id = AsyncMock(return_value=None)

    @asynccontextmanager
    async def factory():
        yield google

    # This test only connects to its loopback listener.
    monkeypatch.setenv("NO_PROXY", "*")
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("NOTEBOOKLM_MCP_TOKEN", token)
    oauth = SelfHostedOAuthProvider(password=secrets.token_urlsafe(32),
                                  base_url="https://simulated.example.com",
                                  state_path=tmp_path / "oauth.json")
    server = create_server(client_factory=factory, auth=build_auth(token, oauth))
    app = server.http_app(stateless_http=True)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    runner = uvicorn.Server(uvicorn.Config(app, log_level="critical", proxy_headers=False))
    task = asyncio.create_task(runner.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not runner.started:
                if task.done():
                    await task
                    raise RuntimeError("Uvicorn stopped before becoming ready")
                await asyncio.sleep(0.01)
        await smoke.verify(argparse.Namespace(url=f"http://127.0.0.1:{port}/mcp",
                           allow_loopback_http=True, oauth=False, discover_only=False,
                           notebook=notebook_id, question="Summarize the sources"))
        google.notebooks.list.assert_awaited_once()
        google.chat.ask.assert_awaited_once()
    finally:
        runner.should_exit = True
        await asyncio.wait_for(task, timeout=10)
        listener.close()
