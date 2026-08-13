from __future__ import annotations

from src import model_fabric
from src.agent_runtime import RuntimeAgentHub
from src.model_fabric import ModelEndpoint, ModelFabric


def test_discovers_every_ollama_model(monkeypatch):
    monkeypatch.setattr(model_fabric, "_request_json", lambda url, **kwargs: {
        "models": [
            {"name": "omni-agent:latest", "digest": "a", "size": 1},
            {"name": "stealth-claw:latest", "digest": "b", "size": 2},
        ]
    })
    fabric = ModelFabric()
    discovered = fabric.discover_ollama()
    assert {endpoint.model for endpoint in discovered} == {"omni-agent:latest", "stealth-claw:latest"}
    assert all(endpoint.free and endpoint.local and endpoint.verified for endpoint in discovered)


def test_kilo_discovery_keeps_free_models_only(monkeypatch):
    monkeypatch.setattr(model_fabric, "_request_json", lambda url, **kwargs: {
        "data": [
            {"id": "vendor/model:free"},
            {"id": "vendor/paid-model"},
            {"id": "openrouter/free"},
        ]
    })
    fabric = ModelFabric()
    discovered = fabric.discover_kilo_free()
    models = {endpoint.model for endpoint in discovered}
    assert "vendor/model:free" in models
    assert "openrouter/free" in models
    assert "kilo-auto/free" in models
    assert "vendor/paid-model" not in models


def test_ollama_chat_returns_real_message(monkeypatch):
    monkeypatch.setattr(model_fabric, "_request_json", lambda url, **kwargs: {
        "message": {"content": "working"},
        "eval_count": 7,
    })
    fabric = ModelFabric()
    endpoint = ModelEndpoint("local", "ollama", "model", "http://local", free=True, local=True)
    result = fabric.chat(endpoint, "hello")
    assert result["status"] == "completed"
    assert result["response"] == "working"
    assert result["eval_count"] == 7


def test_openai_compatible_chat_and_kilo_mode_header(monkeypatch):
    captured = {}

    def fake_request(url, **kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "answer"}}]}

    monkeypatch.setattr(model_fabric, "_request_json", fake_request)
    fabric = ModelFabric()
    endpoint = fabric.register_openai_compatible(
        "kilo-test",
        "kilo-gateway",
        "kilo-auto/free",
        "https://example.invalid/v1",
        free=True,
        optional_auth=True,
    )
    result = fabric.chat(endpoint, "hello", mode="review")
    assert result["status"] == "completed"
    assert captured["headers"]["x-kilocode-mode"] == "review"


def test_fanout_respects_max_agents(monkeypatch):
    fabric = ModelFabric()
    for index in range(5):
        fabric.register(ModelEndpoint(f"e{index}", "ollama", f"m{index}", "http://local", free=True, local=True, verified=True))

    monkeypatch.setattr(fabric, "chat", lambda endpoint, prompt, **kwargs: {
        "status": "completed",
        "endpoint_id": endpoint.endpoint_id,
        "response": endpoint.model,
        "latency_ms": 1,
    })
    results = fabric.fanout("plan", max_agents=3)
    assert len(results) == 3
    assert all(result["status"] == "completed" for result in results)


def test_runtime_router_falls_through_dead_free_endpoint(monkeypatch, tmp_path):
    dead = ModelEndpoint("dead", "ollama", "dead", "http://dead", free=True, local=True, verified=True)
    live = ModelEndpoint("live", "ollama", "live", "http://live", free=True, local=True, verified=True)

    def fake_discover(self):
        self.endpoints = {"dead": dead, "live": live}
        return [dead, live]

    monkeypatch.setattr(ModelFabric, "discover_all", fake_discover)
    hub = RuntimeAgentHub(state_path=str(tmp_path / "state.json"))

    def fake_chat(endpoint, prompt, **kwargs):
        if endpoint.endpoint_id == "dead":
            return {"status": "failed", "error": "offline"}
        return {"status": "completed", "response": "ok", "endpoint_id": endpoint.endpoint_id}

    monkeypatch.setattr(hub.fabric, "chat", fake_chat)
    result = hub.route_query("do work")
    assert result["status"] == "completed"
    assert result["routed"] == "live"
    assert result["attempts_before_success"] == 1
