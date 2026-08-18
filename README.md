# OpenClaw v3.2 — Controlled Runtime + Free-Agent Fabric

> **An agent name is not capability. OpenClaw v3.2 discovers and calls real endpoints, and fails over when one does not work.**

OpenClaw combines file-integrity monitoring, policy-governed computer-user actions, persistent audit receipts, REST/MCP control, authenticated mesh state, and a free-first model fabric.

## What actually runs

The model fabric now supports:

- **Every installed Ollama model**, discovered dynamically from `/api/tags`. Casey/GlacierEQ models such as `omni-agent`, `megamind`, or `stealth-*` become usable automatically when they are actually installed.
- **Kilo Gateway free models**, including the `kilo-auto/free` route and free models returned by the gateway model catalog.
- **Groq** when `GROQ_API_KEY` is configured.
- **OpenRouter free routing** when `OPENROUTER_API_KEY` is configured.
- **MiMo** through its OpenAI-compatible API when `MIMO_API_KEY` is configured.
- **Any OpenAI-compatible local or remote endpoint** declared in `.openclaw/model-fabric.json`.
- **Parallel free-agent fanout** with `OPENCLAW_MAX_PARALLEL_AGENTS` controlling concurrency.
- **Fallback routing**: a dead free endpoint no longer kills the request; OpenClaw continues through the free/local pool until something actually answers.

The old `cline-local`, `kilo-local`, and similar aliases in the legacy hub were not real Cline/Kilo executions. The supported v3.2 path is `src.model_fabric` + `src.agent_runtime`.

## Install and prove

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
python scripts/operate.py
```

## Free-agent CLI

```bash
openclaw-agents discover
openclaw-agents list --filter free
openclaw-agents test
openclaw-agents route --prompt "Find the bug and propose the strongest coherent correct patch that preserves existing capability"
openclaw-agents fanout --prompt "Review this design adversarially and identify the highest-leverage capability improvements" --max-agents 0 --mode review
openclaw-agents query --agent ollama-omni-agent_latest --prompt "Implement the parser as production-quality, elite humanized engineering with complete material failure handling"
```

`--max-agents 0` means every discovered free endpoint. Fanout is intended for independent planning/review/reasoning; it does not pretend several models are the same agent.

## Engineering direction

OpenClaw prompts and routed agents should default to **maximum coherent capability**, not minimum-change doctrine. Small diffs are acceptable when the problem itself is small; they are not a quality target.

Agents should preserve useful existing behavior, search for compatible capability donors, implement the strongest coherent tranche justified by the objective, test integration and failure paths, and avoid translating `full`, `powerful`, `elite`, `complete`, `build up`, `innovate`, or similar Operator direction into MVP/smallest/safest scope.

## Ollama and GlacierEQ models

Set `OLLAMA_HOST` if Ollama is not on the default loopback address. There is no hard-coded model list. Pull or create a model in Ollama and the next discovery sees it.

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
openclaw-agents discover
```

## Kilo free routing

`KILO_API_KEY` is optional for gateway routes that permit anonymous free access and useful when an authenticated Kilo account is available.

```bash
export KILO_API_KEY='your-local-value-if-used'
openclaw-agents discover
openclaw-agents route --cloud-first --prompt "Review this patch"
```

OpenClaw calls Kilo Gateway's OpenAI-compatible API directly. This is separate from the **Kilo Code coding client**, which can consume OpenClaw through MCP as described below.

## MiMo

```bash
export MIMO_API_KEY='your-local-value'
export MIMO_BASE_URL='https://api.xiaomimimo.com/v1'
export MIMO_MODEL='mimo-v2.5-pro'
openclaw-agents discover
```

MiMo is treated as an OpenAI-compatible model endpoint. Plain chat/reasoning calls are supported by the fabric; no claim is made that every provider-specific tool-call history format is interchangeable.

## Custom OpenAI-compatible endpoints

Create `.openclaw/model-fabric.json` locally:

```json
{
  "endpoints": [
    {
      "id": "local-lmstudio",
      "provider": "lmstudio",
      "model": "your-loaded-model-id",
      "base_url": "http://127.0.0.1:1234/v1",
      "free": true,
      "local": true,
      "capabilities": ["chat", "reasoning", "code"]
    }
  ]
}
```

Credentials are referenced by environment-variable name with `api_key_env`; secret values do not belong in this file.

## Kilo Code, Cline, MiMoCode and other coding agents

OpenClaw exposes its whole free-agent fabric as MCP tools. Coding clients that support MCP can use OpenClaw instead of being faked as model aliases.

Start the dedicated agent MCP server:

```bash
export OPENCLAW_MCP_TOKEN='replace-with-local-secret'
openclaw-agent-mcp --http --host 127.0.0.1 --port 8091
```

MCP endpoint:

```text
http://127.0.0.1:8091/mcp
```

Available tools include discovery, listing, probing, direct query, fallback routing, parallel fanout, and provider reports. Configure Kilo Code, Cline, MiMoCode, or another MCP-capable coding client to use that endpoint. If `OPENCLAW_MCP_TOKEN` is set, send it as a bearer token.

This division is intentional:

- OpenClaw directly executes model HTTP endpoints.
- Kilo Code/Cline/MiMoCode remain real coding-agent clients with their own terminal, workspace, approval, and editing behavior.
- MCP gives those agents access to OpenClaw's model pool without falsely claiming OpenClaw itself spawned their CLI.

## Computer-user execution

`OPENCLAW_ACTION_EXECUTED` is returned only when a configured backend reports actual execution. Without a browser/desktop backend, the runtime returns `OPENCLAW_BACKEND_UNAVAILABLE` with `executed=false`.

Optional backends:

```bash
pip install -e '.[gui]'
export OPENCLAW_LOCAL_GUI=1

pip install -e '.[browser]'
export OPENCLAW_BROWSER_CDP_URL='http://127.0.0.1:9222'
```

## REST API

```bash
export OPENCLAW_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export OPENCLAW_AUDIT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python server.py --host 127.0.0.1 --port 8088
```

## Main MCP surface

```bash
python mcp_server.py --stdio
export OPENCLAW_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python mcp_server.py --http --host 127.0.0.1 --port 8089
```

The dedicated free-agent MCP surface is `openclaw-agent-mcp` on port 8091 by default.

## Docker integrity service

```bash
cp .env.example .env
OPENCLAW_WATCH_PATH=/path/to/watch docker compose up --build -d
curl http://127.0.0.1:8088/health
```

## Audit and promotion authority

Action records form a SHA-256 chain and optionally carry HMAC authentication via `OPENCLAW_AUDIT_SECRET`. Promotion grants require `OPENCLAW_PROMOTION_SECRET`; no operator secret is embedded in source.

## License

MIT — GlacierEQ
