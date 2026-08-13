"""OpenClaw v3.1 — governed computer-user runtime with truthful execution receipts."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .action_runtime import ActionBackend, BackendResult, DryRunBackend, NullBackend, SlidingWindowRateLimiter, choose_backend
from .audit_ledger import AuditLedger, redact_value, safe_target

CONFIG_PATH = Path(__file__).resolve().parents[1] / "OPENCLAW_CONFIG.json"


class OpenClawEngine:
    """Policy-bound action engine.

    OpenClaw only reports ``OPENCLAW_ACTION_EXECUTED`` when a configured backend
    confirms that it actually performed the action. A missing desktop/browser
    backend fails closed rather than converting an audit event into fake proof.
    """

    def __init__(
        self,
        agent_id: str = "openclaw-v3.1",
        config_file: Optional[Path] = None,
        *,
        backend: Optional[ActionBackend] = None,
        audit_file: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.config_path = Path(config_file) if config_file else CONFIG_PATH
        self.config = self._load_config()
        policy = self.config.get("policy_governor", {})
        self._allowed = set(policy.get("allowed_action_types", []))
        self._approval_required = set(policy.get("require_human_approval_for", []))
        self._max_retries = max(1, int(policy.get("max_retry_attempts", 1)))
        self._limiter = SlidingWindowRateLimiter(max(1, int(policy.get("max_actions_per_second", 20))))
        self.backend: ActionBackend = backend or choose_backend(self.config)
        ledger_path = audit_file or self.config.get("execution", {}).get("audit_log", ".openclaw/action_audit.jsonl")
        secret_env = self.config.get("execution", {}).get("audit_secret_env", "OPENCLAW_AUDIT_SECRET")
        self.ledger = AuditLedger(str(ledger_path), str(secret_env))

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                value = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
            except (OSError, ValueError):
                pass
        return {
            "version": "3.1.0",
            "openclaw_version": "3.1.0",
            "policy_governor": {
                "allowed_action_types": [
                    "click", "type", "scroll", "navigate", "inspect_dom",
                    "capture_screenshot", "hover", "drag_and_drop", "shortcut",
                    "key_press", "ocr_read_screen", "vision_sample",
                ],
                "max_actions_per_second": 20,
                "max_retry_attempts": 2,
                "require_human_approval_for": [],
            },
            "execution": {"backend": "auto", "audit_log": ".openclaw/action_audit.jsonl"},
        }

    @property
    def action_history(self) -> List[Dict[str, Any]]:
        return self.get_audit_trail()

    def _deny(self, status: str, reason: str, action_type: str, *, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "kind": "action-denial",
            "event_id": f"CLAW-{uuid.uuid4().hex[:16]}",
            "agent_id": self.agent_id,
            "action_type": action_type,
            "status": status,
            "reason": reason,
            "idempotency_key": idempotency_key,
        }
        record = self.ledger.append(payload)
        return {
            "status": status,
            "executed": False,
            "reason": reason,
            "action_type": action_type,
            "event_id": payload["event_id"],
            "audit_record_hash": record["record_hash"],
        }

    def execute_action(
        self,
        action_type: str,
        target: str,
        parameters: Optional[Dict[str, Any]] = None,
        coords: Optional[Tuple[int, int]] = None,
        *,
        principal: str = "local-operator",
        source: str = "direct",
        idempotency_key: Optional[str] = None,
        human_approved: bool = False,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        parameters = dict(parameters or {})
        action_type = str(action_type).strip()
        target = str(target or "")

        if not action_type or action_type not in self._allowed:
            return self._deny(
                "DENIED_BY_AKOS_POLICY",
                f"Action type '{action_type}' not permitted by OpenClaw policy governor.",
                action_type,
                idempotency_key=idempotency_key,
            )
        if action_type in self._approval_required and not human_approved:
            return self._deny(
                "HUMAN_APPROVAL_REQUIRED",
                f"Action type '{action_type}' requires explicit approval.",
                action_type,
                idempotency_key=idempotency_key,
            )
        if idempotency_key:
            previous = self.ledger.find_idempotency(idempotency_key)
            if previous:
                payload = previous.get("payload", {})
                return {
                    "status": "OPENCLAW_ACTION_REPLAYED",
                    "executed": False,
                    "idempotency_key": idempotency_key,
                    "original_event_id": payload.get("event_id"),
                    "original_status": payload.get("status"),
                    "audit_record_hash": previous.get("record_hash"),
                }
        if not self._limiter.allow():
            return self._deny("RATE_LIMITED", "OpenClaw action rate limit exceeded.", action_type, idempotency_key=idempotency_key)
        if not self.backend.available():
            return self._deny(
                "OPENCLAW_BACKEND_UNAVAILABLE",
                "No real execution backend is configured on this host.",
                action_type,
                idempotency_key=idempotency_key,
            )
        if not self.backend.supports(action_type):
            return self._deny(
                "UNSUPPORTED_BY_BACKEND",
                f"Backend '{self.backend.name}' does not implement '{action_type}'.",
                action_type,
                idempotency_key=idempotency_key,
            )

        result: Optional[BackendResult] = None
        attempts = 0
        while attempts < self._max_retries:
            attempts += 1
            result = self.backend.execute(action_type, target, parameters, coords)
            if result.ok or result.status not in {"EXECUTION_FAILED", "TRANSIENT_ERROR"}:
                break
        assert result is not None

        if result.executed and result.ok:
            status = "OPENCLAW_ACTION_EXECUTED"
        elif result.ok and not result.executed:
            status = "OPENCLAW_ACTION_PLANNED"
        else:
            status = "OPENCLAW_ACTION_FAILED"

        event_id = f"CLAW-{uuid.uuid4().hex[:16]}"
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
        payload = {
            "kind": "action",
            "event_id": event_id,
            "agent_id": self.agent_id,
            "principal": principal,
            "source": source,
            "action_type": action_type,
            "target": safe_target(target),
            "coordinates": list(coords) if coords else None,
            "parameters": redact_value(parameters),
            "parameter_digest": hashlib.sha256(json.dumps(parameters, sort_keys=True, default=str).encode()).hexdigest(),
            "idempotency_key": idempotency_key,
            "human_approved": bool(human_approved),
            "backend": result.backend,
            "backend_status": result.status,
            "status": status,
            "executed": bool(result.executed),
            "attempts": attempts,
            "latency_ms": elapsed_ms,
            "result": redact_value(result.detail),
        }
        record = self.ledger.append(payload)
        event = dict(payload)
        event["audit_record_hash"] = record["record_hash"]
        event["audit_prev_hash"] = record["prev_hash"]
        return {
            "status": status,
            "executed": bool(result.executed),
            "openclaw_version": self.config.get("openclaw_version", self.config.get("version", "3.1.0")),
            "backend": result.backend,
            "event": event,
            "result": result.detail,
            "execution_latency_ms": elapsed_ms,
        }

    def sample_vision_state(self, viewport: Tuple[int, int] = (1920, 1080)) -> Dict[str, Any]:
        result = self.execute_action(
            "vision_sample",
            "viewport",
            {"viewport": [int(viewport[0]), int(viewport[1])]},
            source="vision",
        )
        return {
            **result,
            "viewport_dimensions": [int(viewport[0]), int(viewport[1])],
        }

    def get_audit_trail(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.ledger.records(limit=limit)

    def verify_audit_trail(self) -> Dict[str, Any]:
        return self.ledger.verify()

    def health(self) -> Dict[str, Any]:
        verification = self.verify_audit_trail()
        return {
            "status": "healthy" if verification.get("ok") else "degraded",
            "version": self.config.get("version", "3.1.0"),
            "agent_id": self.agent_id,
            "backend": self.backend.name,
            "backend_available": self.backend.available(),
            "audit": verification,
            "allowed_action_types": sorted(self._allowed),
        }


__all__ = [
    "OpenClawEngine",
    "ActionBackend",
    "BackendResult",
    "DryRunBackend",
    "NullBackend",
]


if __name__ == "__main__":
    engine = OpenClawEngine()
    print(json.dumps(engine.health(), indent=2, sort_keys=True))
