from __future__ import annotations

import json
import time

from src.agent_runtime import RuntimeAgentHub
from src.model_fabric import ModelEndpoint, ModelFabric


def install_discovered_endpoint(monkeypatch):
    endpoint = ModelEndpoint("real-agent", "ollama", "real:latest", "http://local", free=True, local=True)

    def fake_discover(self):
        self.endpoints = {endpoint.endpoint_id: endpoint}
        return [endpoint]

    monkeypatch.setattr(ModelFabric, "discover_all", fake_discover)
    return endpoint


def test_recent_observation_state_is_loaded(tmp_path, monkeypatch):
    install_discovered_endpoint(monkeypatch)
    path = tmp_path / "agents_state.json"
    path.write_text(json.dumps({
        "observed_at": time.time(),
        "statuses": {"real-agent": {"status": "verified", "verified": True}},
        "test_results": {"real-agent": {"status": "verified"}},
    }))
    hub = RuntimeAgentHub(str(path), state_ttl_s=60)
    assert hub.agents["real-agent"].status == "verified"
    assert hub.agents["real-agent"].verified is True
    assert hub.get_report()["verified"] == 1


def test_stale_observation_state_is_not_loaded(tmp_path, monkeypatch):
    install_discovered_endpoint(monkeypatch)
    path = tmp_path / "agents_state.json"
    path.write_text(json.dumps({
        "observed_at": time.time() - 1000,
        "statuses": {"real-agent": {"status": "verified", "verified": True}},
    }))
    hub = RuntimeAgentHub(str(path), state_ttl_s=10)
    assert hub.agents["real-agent"].status == "untested"
    assert hub.agents["real-agent"].verified is False


def test_saved_state_contains_observations_not_route_definitions(tmp_path, monkeypatch):
    install_discovered_endpoint(monkeypatch)
    path = tmp_path / "agents_state.json"
    hub = RuntimeAgentHub(str(path))
    hub.agents["real-agent"].status = "failed"
    hub.save_state()
    state = json.loads(path.read_text())
    assert state["statuses"]["real-agent"]["status"] == "failed"
    serialized = path.read_text()
    assert "base_url" not in serialized
    assert "api_key_env" not in serialized
