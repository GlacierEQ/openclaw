#!/usr/bin/env python3
"""OpenClaw Tests — Comprehensive test suite."""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from .integrity.watchdog_daemon import WatchdogDaemon, FileFingerprint, IntegrityEvent
from src.openclaw import OpenClawEngine
from src.promotion_authority import PromotionAuthority, PromotionGrant


class TestWatchdogDaemon:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "state.json")
        self.event_log = os.path.join(self.tmpdir, "events.jsonl")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_initial_scan(self):
        test_file = os.path.join(self.tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello world")

        daemon = WatchdogDaemon(
            watch_dirs=[self.tmpdir],
            state_file=self.state_file,
            event_log=self.event_log,
        )
        result = daemon.initial_scan()
        assert result["status"] == "SCAN_COMPLETE"
        assert result["total_files"] >= 1

    def test_detect_modification(self):
        test_file = os.path.join(self.tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("original content")

        daemon = WatchdogDaemon(
            watch_dirs=[self.tmpdir],
            state_file=self.state_file,
            event_log=self.event_log,
        )
        daemon.initial_scan()
        original_hash = list(daemon.fingerprints.values())[0].sha256

        with open(test_file, "w") as f:
            f.write("modified content")

        result = daemon.check_integrity()
        assert result["changes"] >= 1
        assert any(e["event_type"] == "MODIFIED" for e in result["events"])

    def test_detect_deletion(self):
        test_file = os.path.join(self.tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("to be deleted")

        daemon = WatchdogDaemon(
            watch_dirs=[self.tmpdir],
            state_file=self.state_file,
            event_log=self.event_log,
        )
        daemon.initial_scan()
        os.remove(test_file)

        result = daemon.check_integrity()
        assert any(e["event_type"] == "DELETED" for e in result["events"])

    def test_detect_addition(self):
        daemon = WatchdogDaemon(
            watch_dirs=[self.tmpdir],
            state_file=self.state_file,
            event_log=self.event_log,
        )
        daemon.initial_scan()

        test_file = os.path.join(self.tmpdir, "new.txt")
        with open(test_file, "w") as f:
            f.write("new file")

        result = daemon.check_integrity()
        assert any(e["event_type"] == "ADDED" for e in result["events"])

    def test_exclude_patterns(self):
        py_cache = os.path.join(self.tmpdir, "__pycache__")
        os.makedirs(py_cache)
        with open(os.path.join(py_cache, "test.pyc"), "w") as f:
            f.write("cached")

        daemon = WatchdogDaemon(
            watch_dirs=[self.tmpdir],
            state_file=self.state_file,
            event_log=self.event_log,
        )
        result = daemon.initial_scan()
        assert not any("__pycache__" in k for k in daemon.fingerprints)


class TestOpenClawEngine:
    def test_execute_action_allowed(self):
        engine = OpenClawEngine()
        result = engine.execute_action("click", "button.submit")
        assert result["status"] == "OPENCLAW_ACTION_EXECUTED"

    def test_execute_action_denied(self):
        engine = OpenClawEngine()
        result = engine.execute_action("forbidden_action", "target")
        assert result["status"] == "DENIED_BY_AKOS_POLICY"

    def test_audit_trail(self):
        engine = OpenClawEngine()
        engine.execute_action("click", "a")
        engine.execute_action("type", "input")
        history = engine.get_audit_trail()
        assert len(history) == 2
        assert all("sha256_signature" in e for e in history)

    def test_vision_sample(self):
        engine = OpenClawEngine()
        result = engine.sample_vision_state()
        assert result["status"] == "VISION_SAMPLED"


class TestPromotionAuthority:
    def test_issue_and_verify(self):
        auth = PromotionAuthority(b"test-secret", ttl_s=3600)
        grant = auth.issue("test-repo", "abc123", "def456")
        valid, err = auth.verify(grant)
        assert valid
        assert err is None

    def test_expired_grant(self):
        auth = PromotionAuthority(b"test-secret", ttl_s=0.1)
        grant = auth.issue("test-repo", "abc123", "def456")
        time.sleep(0.2)
        valid, err = auth.verify(grant)
        assert not valid
        assert err == "GRANT_EXPIRED"

    def test_bad_mac(self):
        auth1 = PromotionAuthority(b"secret1")
        auth2 = PromotionAuthority(b"secret2")
        grant = auth1.issue("test-repo", "abc", "def")
        valid, err = auth2.verify(grant)
        assert not valid
        assert err == "BAD_MAC"


def run_all():
    import pytest
    pytest.main([str(Path(__file__).parent), "-v"])


if __name__ == "__main__":
    run_all()
