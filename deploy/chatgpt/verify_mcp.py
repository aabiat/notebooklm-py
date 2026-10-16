#!/usr/bin/env python3
"""Check a real deployment without printing credentials or notebook contents."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from urllib.parse import urlsplit

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


async def verify(args: argparse.Namespace) -> None:
    url = args.url.rstrip("/")
    parsed = urlsplit(url)
    loopback = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (parsed.scheme != "https" and not (loopback and args.allow_loopback_http)) or not parsed.hostname:
        raise ValueError("Use HTTPS, or explicitly allow loopback HTTP for local checks.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/mcp":
        raise ValueError("Use a bare /mcp endpoint, without URL credentials, query or fragment.")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as http:
        for headers in ({}, {"Authorization": "Bearer deliberately-invalid-probe"}):
            response = await http.post(url, headers={"Accept": "application/json, text/event-stream", **headers},
                                       json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            if response.status_code != 401:
                raise RuntimeError(f"Authentication gate expected HTTP 401, got {response.status_code}.")
    print("PASS: unauthenticated and invalid-token requests rejected (401).")
    token = None if args.oauth else os.environ.get("NOTEBOOKLM_MCP_TOKEN")
    if token:
        transport = StreamableHttpTransport(url, headers={"Authorization": f"Bearer {token}"})
        connection = Client(transport, timeout=120)
    else:
        connection = Client(url, auth="oauth", timeout=120)
    async with connection as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        expected = {"notebook_list", "chat_ask", "chat_start", "chat_status", "server_info"}
        if len(names) != 38 or not expected <= names:
            raise RuntimeError(f"Unexpected MCP surface: {len(names)} tools.")
        print("PASS: MCP initialize and tools/list (38 tools).")
        result = await client.call_tool("notebook_list", {"limit": 1})
        if getattr(result, "is_error", False):
            raise RuntimeError("notebook_list returned a tool error.")
        listing = result.structured_content
        if not isinstance(listing, dict) or not isinstance(listing.get("notebooks"), list):
            raise RuntimeError("notebook_list returned an unexpected result shape.")
        print(f"PASS: notebook_list (total={listing.get('total')}; titles and IDs omitted).")
        if args.discover_only:
            print("SKIPPED: chat_ask (--discover-only); full validation remains incomplete.")
            return
        result = await client.call_tool("chat_ask", {"notebook": args.notebook, "question": args.question,
                                                    "references": "full"})
        if getattr(result, "is_error", False):
            raise RuntimeError("chat_ask returned a tool error.")
        answer = result.structured_content
        if not isinstance(answer, dict) or not str(answer.get("answer", "")).strip():
            raise RuntimeError("chat_ask returned no answer.")
        print("PASS: chat_ask returned an answer; private content omitted.")
        print(json.dumps({"answer_characters": len(answer["answer"]),
                          "references": len(answer.get("references", []))}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--notebook", help="Explicit canonical notebook UUID with sources")
    parser.add_argument("--question", default="Resume las ideas principales de las fuentes y cita la evidencia.")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--allow-loopback-http", action="store_true")
    parser.add_argument("--oauth", action="store_true", help="Use browser OAuth even if a bearer env var is available")
    args = parser.parse_args()
    if not args.discover_only and not args.notebook:
        parser.error("--notebook is required unless --discover-only is set.")
    try:
        asyncio.run(verify(args))
    except Exception as exc:
        # Library exception messages may contain private tool results or HTTP material.
        print(f"FAIL: {type(exc).__name__}; inspect the endpoint/auth/profile locally. Details withheld.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
