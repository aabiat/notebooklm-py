# Validation record

Date: 2026-10-15, America/Mexico_City. Upstream code baseline: `4188d7e26a07b6b94b67bf95041c81bc1530c508`.

## Executed and passed

| Check | Observed result | Scope |
| --- | --- | --- |
| Upstream MCP focused suite | 208 passed, 4 deprecation warnings, 18.47s | Manifest, 38 exact tools and annotations, bearer, OAuth discovery/DCR/PKCE/login/persistence/resource binding, bind/entrypoint guards, notebooks and chat adapters |
| Additive deployment checks | 4 passed | Private file permissions, no secret output, no overwrite, reject state inside checkout, reject symlink overwrite; actual loopback HTTP test below |
| Actual TCP loopback MCP transport | initialize → tools/list → notebook_list → chat_ask succeeded; missing/wrong bearer returned 401 | Real Uvicorn/FastMCP HTTP with combined bearer/OAuth provider and stateless transport; Google client replaced with a simulated client |
| Portable plugin schemas | Both plugin.json and mcp.json passed live Agent Plugins 1.0.0 JSON schemas | Structural validation; not registration or installation |
| Shell/Python/YAML | sh -n, compileall, YAML parsing and relevant Compose contract assertions passed | Not a Docker image build or docker compose config validation |
| Changes | Additions limited to deploy/chatgpt; no business-code or dependency edits | main is not updated |

The live public MCP schema rejected the OpenAI docs' per-server `extensions` example. The delivered portable mcp.json therefore contains only the supported streamable-http URL. OAuth/DCR is selected in the ChatGPT connection flow; secrets never belong in the package.

Commands for the focused upstream check:

```bash
.venv/bin/python -m pytest \
  tests/unit/mcp/test_manifest.py \
  tests/unit/mcp/test_remote_auth.py \
  tests/unit/mcp/test_selfhosted_oauth.py \
  tests/unit/mcp/test_entrypoint.py \
  tests/unit/mcp/test_notebooks.py \
  tests/unit/mcp/test_chat.py -q
.venv/bin/python -m pytest deploy/chatgpt/test_deployment.py -q
sh -n deploy/chatgpt/compose.sh
.venv/bin/python -m compileall -q deploy/chatgpt
```

Test environment: Python 3.12.14, notebooklm-py 0.8.5 from this checkout, fastmcp 4.1.0, mcp 2.3.0, httpx 0.28.1, uvicorn 0.54.0. Test dependencies installed separately: pytest, pytest-asyncio, pytest-timeout, pytest-httpx, python-dotenv. The managed environment's SOCKS proxy additionally required `socksio`; no project dependency file was changed. The HTTP fixture sets NO_PROXY for its local test; the environment still controls network policy.

## Not executed / not complete

- Docker image build and Compose lifecycle: Docker unavailable in this execution environment.
- Real Google login and NotebookLM listing/query: no authorized NotebookLM profile or inline Google auth available here. Simulated results are not account access evidence.
- Public DNS/TLS/Cloudflare route: no target hostname, tunnel token or persistent host supplied.
- Site deployment: not attempted because the existing Python/process/filesystem architecture does not match the supported Sites deployment contract. No failed deployment is being represented as runtime experimentation.
- ChatGPT OAuth callback and installed-plugin tool calls: no hosted endpoint or registered plugin exists yet.

## Completion criteria on the target host

1. Build and start the existing Docker server using the new wrapper.
2. Run `verify_mcp.py --discover-only` locally, then run it with an explicit sourced notebook UUID.
3. Run external HTTPS verification with `--oauth` and that UUID.
4. Register the private custom MCP plugin in ChatGPT; complete OAuth and install/connect it.
5. Make actual `notebook_list` and `chat_ask` calls through the installed plugin. Only then describe the end-to-end setup as working.
