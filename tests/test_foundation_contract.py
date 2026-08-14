from __future__ import annotations

import json
import tomllib
from pathlib import Path

from src.mesh_intelligence import MeshIntelligence as CompatMesh
from src.mesh_runtime import MeshIntelligence as CanonicalMesh
from src.openclaw import OpenClawEngine
from src.version import SOURCE_VERSION, VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_version_contract_is_consistent(tmp_path):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "OPENCLAW_CONFIG.json").read_text(encoding="utf-8"))
    assert project["project"]["version"] == SOURCE_VERSION
    assert config["version"] == SOURCE_VERSION
    assert config["openclaw_version"] == SOURCE_VERSION
    engine = OpenClawEngine(audit_file=str(tmp_path / "audit.jsonl"))
    assert engine.health()["version"] == VERSION


def test_mesh_compatibility_surface_is_canonical():
    assert CompatMesh is CanonicalMesh
    assert (ROOT / "src" / "mesh_intelligence.py").stat().st_size < 2000


def test_runtime_state_is_not_source_control_material():
    assert not (ROOT / ".openclaw" / "watchdog_state.json").exists()
    assert not (ROOT / ".openclaw" / "action_audit.jsonl").exists()
    assert not (ROOT / ".openclaw" / "agents_state.json").exists()


def test_control_planes_default_to_loopback_and_authentication():
    config = json.loads((ROOT / "OPENCLAW_CONFIG.json").read_text(encoding="utf-8"))
    for name in ("api", "mcp"):
        section = config[name]
        assert section["host"] in {"127.0.0.1", "localhost", "::1"}
        assert section["require_token"] is True
        assert section["token_env"]
