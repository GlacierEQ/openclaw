from __future__ import annotations

import json

from src.action_runtime import BackendResult, NullBackend
from src.openclaw import OpenClawEngine


class RecordingBackend:
    name = "recording"

    def available(self):
        return True

    def supports(self, action_type):
        return action_type in {"click", "type", "vision_sample"}

    def execute(self, action_type, target, parameters, coords):
        return BackendResult(True, True, self.name, "EXECUTED", {"action_type": action_type, "coords": coords})


def test_execution_requires_backend_receipt(tmp_path):
    engine = OpenClawEngine(backend=RecordingBackend(), audit_file=str(tmp_path / "audit.jsonl"))
    result = engine.execute_action("click", "button.submit", coords=(10, 20))
    assert result["status"] == "OPENCLAW_ACTION_EXECUTED"
    assert result["executed"] is True
    assert result["event"]["backend"] == "recording"


def test_missing_backend_fails_closed(tmp_path):
    engine = OpenClawEngine(backend=NullBackend(), audit_file=str(tmp_path / "audit.jsonl"))
    result = engine.execute_action("click", "button.submit", coords=(10, 20))
    assert result["status"] == "OPENCLAW_BACKEND_UNAVAILABLE"
    assert result["executed"] is False
    continuation = result["continuation"]
    assert continuation["kind"] == "host_activation"
    assert continuation["capability"] == "real execution backend"
    assert continuation["external_action_authorized"] is False
    assert "register_desktop_or_browser_host_adapter" in continuation["next_actions"]


def test_policy_denial_is_not_execution(tmp_path):
    engine = OpenClawEngine(backend=RecordingBackend(), audit_file=str(tmp_path / "audit.jsonl"))
    result = engine.execute_action("not_in_policy", "target")
    assert result["status"] == "DENIED_BY_AKOS_POLICY"
    assert result["executed"] is False


def test_idempotency_prevents_duplicate_execution(tmp_path):
    engine = OpenClawEngine(backend=RecordingBackend(), audit_file=str(tmp_path / "audit.jsonl"))
    first = engine.execute_action("click", "a", coords=(1, 2), idempotency_key="same")
    second = engine.execute_action("click", "a", coords=(1, 2), idempotency_key="same")
    assert first["status"] == "OPENCLAW_ACTION_EXECUTED"
    assert second["status"] == "OPENCLAW_ACTION_REPLAYED"
    assert second["executed"] is False


def test_sensitive_text_is_redacted_from_audit(tmp_path):
    engine = OpenClawEngine(backend=RecordingBackend(), audit_file=str(tmp_path / "audit.jsonl"))
    engine.execute_action("type", "#field", {"text": "example-sensitive-value"})
    serialized = (tmp_path / "audit.jsonl").read_text()
    assert "example-sensitive-value" not in serialized
    record = json.loads(serialized.splitlines()[-1])
    assert record["payload"]["parameters"]["text"]["redacted"] is True


def test_vision_result_is_backend_observed(tmp_path):
    engine = OpenClawEngine(backend=RecordingBackend(), audit_file=str(tmp_path / "audit.jsonl"))
    result = engine.sample_vision_state((800, 600))
    assert result["status"] == "OPENCLAW_ACTION_EXECUTED"
    assert result["viewport_dimensions"] == [800, 600]
    assert "ocr_elements_detected" not in result
