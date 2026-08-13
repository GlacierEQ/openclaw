from __future__ import annotations

import json
import time

from src.agent_runtime import RuntimeAgentHub


def test_recent_observation_state_is_loaded(tmp_path):
    path = tmp_path / "agents_state.json"
    path.write_text(json.dumps({
        "observed_at": time.time(),
        "statuses": {"stealth-team": "verified"},
        "test_results": {"stealth-team": {"status": "verified", "response_preview": "ok"}}
    }))
    hub = RuntimeAgentHub(str(path), state_ttl_s=60)
    assert hub.agents["stealth-team"].status == "verified"
    assert hub.get_report()["verified"] == 1


def test_stale_observation_state_is_not_loaded(tmp_path):
    path = tmp_path / "agents_state.json"
    path.write_text(json.dumps({
        "observed_at": time.time() - 1000,
        "statuses": {"stealth-team": "verified"}
    }))
    hub = RuntimeAgentHub(str(path), state_ttl_s=10)
    assert hub.agents["stealth-team"].status == "untested"


def test_saved_state_contains_observations_not_route_definitions(tmp_path):
    path = tmp_path / "agents_state.json"
    hub = RuntimeAgentHub(str(path))
    hub.agents["stealth-team"].status = "failed"
    hub.save_state()
    state = json.loads(path.read_text())
    assert state["statuses"]["stealth-team"] == "failed"
    assert "endpoint" not in path.read_text()
    assert "model" not in path.read_text()
