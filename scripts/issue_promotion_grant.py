#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.promotion_authority import PromotionAuthority


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a short-lived OpenClaw promotion grant")
    parser.add_argument("--proof", default="machine/proof_receipt.json")
    parser.add_argument("--output", default="machine/promotion_authority.json")
    parser.add_argument("--ttl", type=float, default=3600.0)
    args = parser.parse_args()

    secret_value = os.getenv("OPENCLAW_PROMOTION_SECRET")
    if not secret_value:
        print(json.dumps({"ok": False, "error": "OPENCLAW_PROMOTION_SECRET_NOT_SET"}, indent=2))
        return 1

    proof_path = Path(args.proof)
    proof_bytes = proof_path.read_bytes()
    proof = json.loads(proof_bytes.decode("utf-8"))
    source_sha = str(proof.get("source_sha") or proof.get("verified_code_commit") or "")
    if not source_sha:
        print(json.dumps({"ok": False, "error": "PROOF_SOURCE_SHA_MISSING"}, indent=2))
        return 1

    proof_digest = hashlib.sha256(proof_bytes).hexdigest()
    authority = PromotionAuthority(secret_value.encode("utf-8"), ttl_s=args.ttl)
    grant = authority.issue("GlacierEQ/openclaw", source_sha, proof_digest)
    state = {
        "schema": "openclaw.promotion-authority-state.v2",
        "repository": "GlacierEQ/openclaw",
        "status": "ACTIVE",
        "active_grant": grant.__dict__,
        "grant_fingerprint": grant.fingerprint(),
        "required_secret_env": "OPENCLAW_PROMOTION_SECRET",
        "issued_at": time.time()
    }
    Path(args.output).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "output": args.output, "grant_fingerprint": grant.fingerprint(), "not_after": grant.not_after}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
