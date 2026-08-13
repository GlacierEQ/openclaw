"""Host-local persistence layer for the OpenClaw agent hub."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

from .agent_hub import FreeTierAgentHub


class RuntimeAgentHub(FreeTierAgentHub):
    """Agent hub whose verification state is host-local and time-bounded.

    Source defines candidate routes. A route becomes verified only after this
    host has observed a successful probe, and that observation expires.
    """

    def __init__(self, state_path: str = ".openclaw/agents_state.json", state_ttl_s: float = 900.0):
        self.state_path = Path(state_path)
        self.state_ttl_s = float(state_ttl_s)
        super().__init__(config_path=str(self.state_path))
        self._load_runtime_state()

    def _load_runtime_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            observed_at = float(state.get("observed_at", 0))
            if observed_at <= 0 or time.time() - observed_at > self.state_ttl_s:
                return
            statuses = state.get("statuses", {})
            for name, status in statuses.items():
                if name in self.agents and status in {"verified", "failed", "untested"}:
                    self.agents[name].status = status
            results = state.get("test_results", {})
            self.test_results = results if isinstance(results, dict) else {}
        except (OSError, ValueError, TypeError):
            return

    def test_agent(self, agent_name: str) -> Dict:
        result = super().test_agent(agent_name)
        if result.get("status") == "verified" and not str(result.get("response_preview", "")).strip():
            self.agents[agent_name].status = "failed"
            result = {
                "status": "failed",
                "error": "EMPTY_RESPONSE",
                "latency_ms": result.get("latency_ms", 0),
            }
            self.test_results[agent_name] = result
        return result

    def save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "schema": "openclaw.agent-observation-state.v1",
            "observed_at": time.time(),
            "ttl_seconds": self.state_ttl_s,
            "statuses": {name: agent.status for name, agent in self.agents.items()},
            "test_results": self.test_results,
            "report": self.get_report(),
        }
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["RuntimeAgentHub"]
