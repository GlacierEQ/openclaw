from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit

_SENSITIVE_KEYS = {
    "password", "passwd", "secret", "token", "api_key", "apikey", "authorization",
    "cookie", "cookies", "text", "value", "content", "prompt", "message",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def redact_value(value: Any, key: str = "") -> Any:
    key_l = key.lower()
    if any(marker in key_l for marker in _SENSITIVE_KEYS):
        raw = str(value)
        return {"redacted": True, "length": len(raw), "sha256": hashlib.sha256(raw.encode()).hexdigest()}
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item, key) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def safe_target(target: str) -> Dict[str, Any]:
    if not target:
        return {"display": "", "sha256": hashlib.sha256(b"").hexdigest()}
    try:
        parts = urlsplit(target)
        if parts.scheme and parts.netloc:
            display = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        else:
            display = target[:256]
    except Exception:
        display = target[:256]
    return {"display": display, "sha256": hashlib.sha256(target.encode()).hexdigest()}


class AuditLedger:
    """Append-only hash-chain audit ledger.

    If ``OPENCLAW_AUDIT_SECRET`` (or another configured environment variable)
    is present, each record also receives an HMAC over its record hash. The
    ledger remains verifiable as a plain SHA-256 chain without the secret, but
    HMAC verification provides operator-authenticated integrity.
    """

    def __init__(self, path: str = ".openclaw/action_audit.jsonl", secret_env: str = "OPENCLAW_AUDIT_SECRET"):
        self.path = Path(path)
        self.secret_env = secret_env
        self._lock = threading.Lock()
        self._last_hash = self._read_last_hash()

    def _secret(self) -> Optional[bytes]:
        value = os.getenv(self.secret_env)
        return value.encode("utf-8") if value else None

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        try:
            lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not lines:
                return "0" * 64
            return str(json.loads(lines[-1])["record_hash"])
        except Exception:
            return "CORRUPT"

    def append(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if self._last_hash == "CORRUPT":
                raise RuntimeError("audit ledger is corrupt; refusing to append")
            base = {
                "schema": "openclaw.audit-record.v1",
                "timestamp": time.time(),
                "prev_hash": self._last_hash,
                "payload": payload,
            }
            record_hash = _digest(base)
            secret = self._secret()
            record = dict(base)
            record["record_hash"] = record_hash
            record["mac"] = hmac.new(secret, record_hash.encode(), hashlib.sha256).hexdigest() if secret else None
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._last_hash = record_hash
            return record

    def records(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except Exception:
            return []
        return rows[-limit:] if limit else rows

    def verify(self) -> Dict[str, Any]:
        previous = "0" * 64
        count = 0
        secret = self._secret()
        for index, record in enumerate(self.records(), start=1):
            if record.get("prev_hash") != previous:
                return {"ok": False, "records": count, "error": "CHAIN_BREAK", "index": index}
            base = {
                "schema": record.get("schema"),
                "timestamp": record.get("timestamp"),
                "prev_hash": record.get("prev_hash"),
                "payload": record.get("payload"),
            }
            expected = _digest(base)
            if not hmac.compare_digest(expected, str(record.get("record_hash", ""))):
                return {"ok": False, "records": count, "error": "HASH_MISMATCH", "index": index}
            mac = record.get("mac")
            if secret and mac:
                expected_mac = hmac.new(secret, expected.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected_mac, str(mac)):
                    return {"ok": False, "records": count, "error": "MAC_MISMATCH", "index": index}
            previous = expected
            count += 1
        return {"ok": True, "records": count, "head": previous, "hmac_enabled": bool(secret)}

    def find_idempotency(self, key: str) -> Optional[Dict[str, Any]]:
        for record in reversed(self.records()):
            payload = record.get("payload", {})
            if payload.get("kind") == "action" and payload.get("idempotency_key") == key:
                return record
        return None


__all__ = ["AuditLedger", "redact_value", "safe_target"]
