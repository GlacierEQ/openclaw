"""Compatibility agent hub backed by the OpenClaw model fabric."""
from __future__ import annotations

from typing import Any, Dict, List

from .model_fabric import ModelFabric


class RuntimeAgentHub:
    def __init__(self, state_path: str = ".openclaw/agents_state.json", state_ttl_s: float = 900.0, fabric_config: str | None = None):
        self.state_path = state_path
        self.state_ttl_s = state_ttl_s
        self.fabric = ModelFabric(config_path=fabric_config)
        self.fabric.discover_all()
        self.agents = self.fabric.endpoints
        self.test_results: Dict[str, Dict[str, Any]] = {}

    def discover(self) -> List[Dict[str, Any]]:
        self.fabric.discover_all()
        self.agents = self.fabric.endpoints
        return [endpoint.to_dict() for endpoint in self.agents.values()]

    def save_state(self) -> None:
        return None

    def test_agent(self, agent_name: str) -> Dict[str, Any]:
        endpoint = self.agents.get(agent_name)
        if endpoint is None:
            return {"status": "failed", "error": "AGENT_NOT_FOUND", "agent_id": agent_name}
        result = self.fabric.probe(endpoint)
        self.test_results[agent_name] = result
        return {"agent_id": agent_name, **result}

    def test_all(self) -> Dict[str, Dict[str, Any]]:
        return {name: self.test_agent(name) for name in list(self.agents)}

    def query(self, agent_name: str, prompt: str, system: str = "You are a coding assistant.", mode: str = "code") -> Dict[str, Any]:
        endpoint = self.agents.get(agent_name)
        if endpoint is None:
            return {"status": "failed", "error": "AGENT_NOT_FOUND", "agent_id": agent_name}
        return self.fabric.chat(endpoint, prompt, system=system, mode=mode)

    def route_query(self, prompt: str, prefer_local: bool = True, system: str = "You are a coding assistant.", mode: str = "code") -> Dict[str, Any]:
        self.discover()
        candidates = [endpoint for endpoint in self.fabric.free_first() if endpoint.free]
        candidates.sort(key=lambda endpoint: ((not endpoint.local) if prefer_local else endpoint.local, not endpoint.verified, endpoint.provider, endpoint.model))
        attempts = []
        for endpoint in candidates:
            result = self.fabric.chat(endpoint, prompt, system=system, mode=mode)
            if result.get("status") == "completed":
                return {"routed": endpoint.endpoint_id, "attempts_before_success": len(attempts), **result}
            attempts.append({"agent_id": endpoint.endpoint_id, "provider": endpoint.provider, "model": endpoint.model, "error": result.get("error") or result.get("status")})
        return {"status": "failed", "error": "NO_WORKING_FREE_AGENT", "attempts": attempts}

    def fanout(self, prompt: str, max_agents: int = 0, system: str = "You are a coding assistant.", mode: str = "plan") -> Dict[str, Any]:
        self.discover()
        results = self.fabric.fanout(prompt, max_agents=max_agents, system=system, mode=mode, verified_only=False)
        completed = sum(result.get("status") == "completed" for result in results)
        return {"status": "completed" if completed else "failed", "agents_run": len(results), "completed": completed, "results": results}

    def get_verified_agents(self) -> List[Dict[str, Any]]:
        return [endpoint.to_dict() for endpoint in self.agents.values() if endpoint.verified]

    def get_local_agents(self) -> List[Dict[str, Any]]:
        return [endpoint.to_dict() for endpoint in self.agents.values() if endpoint.local]

    def get_free_agents(self) -> List[Dict[str, Any]]:
        return [endpoint.to_dict() for endpoint in self.agents.values() if endpoint.free]

    def get_report(self) -> Dict[str, Any]:
        values = list(self.agents.values())
        return {
            "total_agents": len(values),
            "verified": sum(endpoint.verified for endpoint in values),
            "free": sum(endpoint.free for endpoint in values),
            "local": sum(endpoint.local for endpoint in values),
            "providers": {provider: sum(endpoint.provider == provider for endpoint in values) for provider in sorted({endpoint.provider for endpoint in values})},
            "strategy": "free-local-first-with-fallback",
        }


__all__ = ["RuntimeAgentHub"]
