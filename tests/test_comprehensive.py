from __future__ import annotations

from src.integrity import WatchdogDaemon


def make_daemon(tmp_path):
    watched = tmp_path / "watched"
    watched.mkdir()
    daemon = WatchdogDaemon(
        [str(watched)],
        state_file=str(tmp_path / "state.json"),
        event_log=str(tmp_path / "events.jsonl"),
    )
    return watched, daemon


def test_initial_scan_and_hash_baseline(tmp_path):
    watched, daemon = make_daemon(tmp_path)
    (watched / "sample.txt").write_text("hello")
    result = daemon.initial_scan()
    assert result["status"] == "SCAN_COMPLETE"
    assert result["total_files"] == 1
    assert len(daemon.fingerprints) == 1


def test_modification_is_detected(tmp_path):
    watched, daemon = make_daemon(tmp_path)
    target = watched / "sample.txt"
    target.write_text("before")
    daemon.initial_scan()
    target.write_text("after")
    result = daemon.check_integrity()
    assert result["changes"] == 1
    assert result["events"][0]["event_type"] == "MODIFIED"


def test_runtime_state_is_excluded(tmp_path):
    watched, daemon = make_daemon(tmp_path)
    runtime = watched / ".openclaw"
    runtime.mkdir()
    (runtime / "state.json").write_text("{}")
    assert daemon.initial_scan()["total_files"] == 0


def test_baseline_survives_restart(tmp_path):
    watched, daemon = make_daemon(tmp_path)
    (watched / "sample.txt").write_text("stable")
    daemon.initial_scan()
    restarted = WatchdogDaemon(
        [str(watched)],
        state_file=str(tmp_path / "state.json"),
        event_log=str(tmp_path / "events.jsonl"),
    )
    assert len(restarted.fingerprints) == 1
    assert restarted.check_integrity()["changes"] == 0
