"""Persistent observation state for discovered OpenClaw model endpoints."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


class AgentObservationStore:
    def __init__(self, path: str, ttl_s: float = 900.0):
        self.path = Path(path)
        self.ttl_s = float(ttl_s)

    def load(self, endpoints: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("observed_at", 0)) > self.ttl_s:
                return {}
            statuses = payload.get("statuses", {})
            for endpoint_id, observed in statuses.items():
                endpoint = endpoints.get(endpoint_id)
                if endpoint is None:
                    continue
                if isinstance(observed, str):
                    endpoint.status = observed
                    endpoint.verified = observed == "verified"
                elif isinstance(observed, dict):
                    endpoint.status = str(observed.get("status", endpoint.status))
                    endpoint.verified = bool(observed.get("verified", endpoint.verified))
            results = payload.get("test_results", {})
            return results if isinstance(results, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def save(self, endpoints: Dict[str, Any], test_results: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "openclaw.agent-observation-state.v2",
            "observed_at": time.time(),
            "ttl_seconds": self.ttl_s,
            "statuses": {
                endpoint_id: {"status": endpoint.status, "verified": endpoint.verified}
                for endpoint_id, endpoint in endpoints.items()
            },
            "test_results": test_results,
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["AgentObservationStore"]
