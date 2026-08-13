"""Short-lived HMAC promotion grants bound to a proof receipt.

The operator secret is never embedded in source. A public reference secret is
not authority. Set ``OPENCLAW_PROMOTION_SECRET`` or pass a secret explicitly.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def operator_secret(secret: Optional[bytes] = None, env: str = "OPENCLAW_PROMOTION_SECRET") -> Optional[bytes]:
    if secret:
        return secret
    value = os.getenv(env)
    return value.encode() if value else None


@dataclass(frozen=True)
class PromotionGrant:
    repository: str
    source_sha: str
    proof_receipt_digest: str
    not_after: float
    mac: str

    def fingerprint(self) -> str:
        return _digest({
            "repository": self.repository,
            "source_sha": self.source_sha,
            "proof_receipt_digest": self.proof_receipt_digest,
            "not_after": self.not_after,
            "mac": self.mac,
        })

    @classmethod
    def from_dict(cls, value: dict) -> "PromotionGrant":
        return cls(
            repository=str(value["repository"]),
            source_sha=str(value["source_sha"]),
            proof_receipt_digest=str(value["proof_receipt_digest"]),
            not_after=float(value["not_after"]),
            mac=str(value["mac"]),
        )


class PromotionAuthority:
    def __init__(self, secret: bytes, ttl_s: float = 3600.0):
        if not secret:
            raise ValueError("secret required")
        if ttl_s <= 0:
            raise ValueError("ttl_s must be > 0")
        self._secret = bytes(secret)
        self._ttl = float(ttl_s)

    def issue(self, repository: str, source_sha: str, proof_receipt_digest: str, now: Optional[float] = None) -> PromotionGrant:
        if not repository or not source_sha or not proof_receipt_digest:
            raise ValueError("repository, source_sha, and proof_receipt_digest are required")
        current = time.time() if now is None else float(now)
        not_after = current + self._ttl
        body = f"{repository}|{source_sha}|{proof_receipt_digest}|{not_after}"
        mac = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        return PromotionGrant(repository, source_sha, proof_receipt_digest, not_after, mac)

    def verify(self, grant: PromotionGrant, now: Optional[float] = None) -> tuple[bool, Optional[str]]:
        current = time.time() if now is None else float(now)
        if current > grant.not_after:
            return False, "GRANT_EXPIRED"
        body = f"{grant.repository}|{grant.source_sha}|{grant.proof_receipt_digest}|{grant.not_after}"
        expected = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, grant.mac):
            return False, "BAD_MAC"
        return True, None


def verify_bound_grant(
    grant_dict: dict,
    proof_receipt_path: str | bytes | Path,
    *,
    secret: Optional[bytes] = None,
    secret_env: str = "OPENCLAW_PROMOTION_SECRET",
    now: Optional[float] = None,
) -> tuple[bool, Optional[str]]:
    resolved_secret = operator_secret(secret, secret_env)
    if not resolved_secret:
        return False, "OPERATOR_SECRET_MISSING"
    path = Path(proof_receipt_path)
    if not path.is_file():
        return False, "PROOF_RECEIPT_MISSING"
    proof_bytes = path.read_bytes()
    file_digest = hashlib.sha256(proof_bytes).hexdigest()
    try:
        proof = json.loads(proof_bytes.decode())
    except Exception:
        return False, "PROOF_RECEIPT_INVALID_JSON"
    if grant_dict.get("proof_receipt_digest") != file_digest:
        return False, "PROOF_DIGEST_MISMATCH"
    if grant_dict.get("source_sha") != proof.get("source_sha"):
        return False, "SOURCE_SHA_MISMATCH"
    try:
        grant = PromotionGrant.from_dict(grant_dict)
    except Exception:
        return False, "GRANT_MALFORMED"
    authority = PromotionAuthority(resolved_secret, ttl_s=max(1.0, grant.not_after - (time.time() if now is None else now) + 1.0))
    return authority.verify(grant, now=now)
