# OpenClaw v3.0 — Production File Integrity Watchdog & Action Governor

> **Autonomous file integrity monitoring with cryptographic audit trails and governed computer-user actions.**

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

---

## What OpenClaw Does

OpenClaw is a production-grade file integrity watchdog that:

- **Monitors** directories in real-time with SHA-256 fingerprinting
- **Detects** modifications, additions, and deletions with severity levels
- **Governs** computer-user actions with cryptographic audit trails
- **Integrates** with AI agents via MCP (Model Context Protocol)
- **Exposes** a REST API for programmatic access

## Architecture

```
OpenClaw v3.0
├── Watchdog Daemon — Real-time file monitoring (SHA-256)
├── Action Engine — Governed computer-user actions
├── API Server — REST endpoints on port 8088
├── MCP Server — Agent integration (stdio/SSE)
├── CLI — Command-line interface
└── Promotion Authority — HMAC-based grant verification
```

## Quick Start

```bash
# Scan directories
python3 cli.py scan --dirs . /path/to/monitor

# Check integrity
python3 cli.py check --dirs .

# Run as daemon
python3 cli.py daemon --dirs . --interval 2

# Execute governed action
python3 cli.py action --type click --target "button.submit" --x 100 --y 200

# Start API server
python3 server.py --port 8088

# Start MCP server
python3 mcp_server.py --stdio
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |
| GET | `/integrity/status` | Tracked files and recent events |
| GET | `/integrity/check` | Run integrity check |
| GET | `/integrity/scan` | Initial directory scan |
| GET | `/engine/history` | Action audit trail |
| GET | `/engine/stats` | Engine statistics |
| POST | `/engine/action` | Execute governed action |
| POST | `/engine/vision` | Vision/OCR sampling |
| POST | `/integrity/add-watch` | Add directory to watch list |

## MCP Tools

| Tool | Description |
|------|-------------|
| `openclaw_audit_integrity` | Audit file integrity with SHA-256 |
| `openclaw_scan_directory` | Initial directory scan |
| `openclaw_execute_action` | Execute governed action |
| `openclaw_get_audit_trail` | Retrieve audit trail |
| `openclaw_vision_sample` | Viewport state sampling |
| `openclaw_health_check` | Service health check |

## Configuration

Edit `OPENCLAW_CONFIG.json`:

```json
{
  "watchdog": {
    "poll_interval_seconds": 2.0,
    "exclude_patterns": [".git", "__pycache__"]
  },
  "policy_governor": {
    "allowed_action_types": ["click", "type", "navigate"]
  }
}
```

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test
python3 -m pytest tests/test_comprehensive.py::TestWatchdogDaemon -v
```

## Deployment

```bash
# Docker
docker build -t openclaw .
docker run -p 8088:8088 openclaw

# Direct
python3 server.py --host 0.0.0.0 --port 8088
```

## License

MIT — GlacierEQ
