from __future__ import annotations

import hashlib
import json
import time

from src.promotion_authority import PromotionAuthority, verify_bound_grant


def test_issue_verify_and_expiry():
    authority = PromotionAuthority(b"test-secret", ttl_s=1)
    grant = authority.issue("repo", "sha", "proof", now=10)
    assert authority.verify(grant, now=10.5) == (True, None)
    assert authority.verify(grant, now=12) == (False, "GRANT_EXPIRED")


def test_bound_grant_requires_private_operator_secret(tmp_path):
    proof = tmp_path / "proof.json"
    proof.write_text(json.dumps({"source_sha": "abc"}))
    digest = hashlib.sha256(proof.read_bytes()).hexdigest()
    authority = PromotionAuthority(b"private-test-key", ttl_s=100)
    grant = authority.issue("repo", "abc", digest, now=time.time())
    assert verify_bound_grant(grant.__dict__, proof, secret=b"private-test-key")[0] is True
    ok, error = verify_bound_grant(grant.__dict__, proof, secret=None, secret_env="OPENCLAW_TEST_SECRET_NOT_SET")
    assert ok is False
    assert error == "OPERATOR_SECRET_MISSING"
