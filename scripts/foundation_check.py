#!/usr/bin/env python3
"""Fail CI when foundational OpenClaw invariants drift."""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.version import SOURCE_VERSION


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FOUNDATION CHECK FAILED: {message}")


def main() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "OPENCLAW_CONFIG.json").read_text(encoding="utf-8"))

    project_version = str(pyproject["project"]["version"])
    require(project_version == SOURCE_VERSION, f"pyproject version {project_version} != {SOURCE_VERSION}")
    require(str(config.get("version")) == SOURCE_VERSION, "OPENCLAW_CONFIG version drift")
    require(str(config.get("openclaw_version")) == SOURCE_VERSION, "OPENCLAW_CONFIG openclaw_version drift")

    for section in ("api", "mcp"):
        cfg = config.get(section, {})
        require(cfg.get("host") in {"127.0.0.1", "localhost", "::1"}, f"{section} default bind must be loopback")
        require(cfg.get("require_token") is True, f"{section} authentication must default on")
        require(bool(str(cfg.get("token_env", "")).strip()), f"{section} token env is required")

    forbidden_state = [
        ROOT / ".openclaw" / "watchdog_state.json",
        ROOT / ".openclaw" / "action_audit.jsonl",
        ROOT / ".openclaw" / "agents_state.json",
    ]
    require(not any(path.exists() for path in forbidden_state), "host-local runtime state is committed")

    legacy_baseline = ROOT / ".integrity" / "file_hashes.json"
    if legacy_baseline.exists():
        baseline = json.loads(legacy_baseline.read_text(encoding="utf-8"))
        require(baseline.get("fingerprints") == {}, "legacy integrity template must never contain host fingerprints")

    mesh_compat = ROOT / "src" / "mesh_intelligence.py"
    require(mesh_compat.stat().st_size < 2000, "legacy mesh implementation returned; canonical runtime must stay singular")

    scripts = pyproject["project"].get("scripts", {})
    required_scripts = {"openclaw", "openclaw-api", "openclaw-mcp", "openclaw-agents", "openclaw-agent-mcp"}
    require(required_scripts <= set(scripts), "required installed entry points missing")

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    effective_lines = [line.strip() for line in requirements.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    require(effective_lines == ["-e .[dev]"], "requirements.txt duplicated dependency authority")

    print(json.dumps({
        "schema": "openclaw.foundation-check.v1",
        "ok": True,
        "version": SOURCE_VERSION,
        "checks": [
            "version_consistency",
            "loopback_defaults",
            "authentication_defaults",
            "runtime_state_hygiene",
            "single_mesh_implementation",
            "entrypoint_integrity",
            "dependency_authority",
        ],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
