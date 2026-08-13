# OpenClaw v3.1 — Controlled Automation Runtime & Integrity Watchdog

> **Real actions require a real execution backend. OpenClaw never converts an audit event into an execution claim.**

This is GlacierEQ's independent OpenClaw implementation: a local/connected-host runtime for file-integrity monitoring, policy-governed computer-user actions, persistent audit receipts, REST/MCP control, and agent routing.

## v3.1 runtime

- SHA-256 baselines with modification/addition/deletion detection
- atomic watchdog state persistence and restart-safe event history
- real backend contract with fail-closed execution semantics
- optional desktop execution through PyAutoGUI
- optional browser execution through Playwright + Chromium CDP
- persistent hash-chained action audit ledger with optional HMAC
- sensitive parameter redaction, idempotency, rate limiting, bounded retries
- authenticated FastAPI REST control plane
- MCP JSON-RPC over stdio or authenticated HTTP
- Docker/Compose integrity service and deterministic CI proof

## Execution truth

`OPENCLAW_ACTION_EXECUTED` is returned only when a configured backend reports that it actually performed the action. Without a browser/desktop backend, the runtime returns `OPENCLAW_BACKEND_UNAVAILABLE` with `executed=false`. Dry-run planning never reports execution.

## Install and prove

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
python scripts/operate.py
```

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

Read-only health/status endpoints are available on the bind interface. Mutating endpoints require bearer authentication by default. The production config binds to loopback unless explicitly overridden.

## MCP

```bash
python mcp_server.py --stdio
export OPENCLAW_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python mcp_server.py --http --host 127.0.0.1 --port 8089
```

## Docker integrity service

```bash
cp .env.example .env
# replace placeholders locally
OPENCLAW_WATCH_PATH=/path/to/watch docker compose up --build -d
curl http://127.0.0.1:8088/health
```

The watched directory is mounted read-only. A headless container is an integrity/API deployment and does not pretend to be a desktop GUI executor.

## Audit and promotion authority

Action records form a SHA-256 chain and optionally carry HMAC authentication via `OPENCLAW_AUDIT_SECRET`. Promotion grants require `OPENCLAW_PROMOTION_SECRET`; no operator secret is embedded in source.

```bash
python scripts/verify_promotion_grant.py
```

The deterministic proof verifies control-path behavior. It separately reports whether the current host has an actual production execution backend, so test execution is never mislabeled as host deployment.

## License

MIT — GlacierEQ
