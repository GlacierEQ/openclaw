#!/usr/bin/env python3
"""OpenClaw Watchdog Daemon — Production file integrity monitoring."""

import hashlib
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone


@dataclass
class FileFingerprint:
    path: str
    sha256: str
    size: int
    mtime: float
    first_seen: float
    last_verified: float

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "FileFingerprint":
        return cls(**d)


@dataclass
class IntegrityEvent:
    event_type: str
    path: str
    old_hash: Optional[str]
    new_hash: Optional[str]
    timestamp: float
    severity: str

    def to_dict(self) -> Dict:
        return asdict(self)


class WatchdogDaemon:
    """Production file integrity watchdog with real-time monitoring."""

    def __init__(
        self,
        watch_dirs: List[str],
        state_file: str = ".openclaw/watchdog_state.json",
        event_log: str = ".openclaw/watchdog_events.jsonl",
        poll_interval: float = 2.0,
        exclude_patterns: Optional[List[str]] = None,
    ):
        self.watch_dirs = [Path(d).resolve() for d in watch_dirs]
        self.state_file = Path(state_file)
        self.event_log = Path(event_log)
        self.poll_interval = poll_interval
        self.exclude_patterns = exclude_patterns or [
            ".git", "__pycache__", "node_modules", ".DS_Store",
            ".openclaw", "*.pyc", ".env"
        ]
        self.fingerprints: Dict[str, FileFingerprint] = {}
        self.events: List[IntegrityEvent] = []
        self.running = False
        self._load_state()

    def _should_exclude(self, path: Path) -> bool:
        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                if path.name.endswith(pattern[1:]):
                    return True
            elif pattern in str(path):
                return True
        return False

    def _compute_hash(self, filepath: Path) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _scan_directory(self, directory: Path) -> Dict[str, FileFingerprint]:
        fingerprints = {}
        try:
            for root, dirs, files in os.walk(directory):
                root_path = Path(root)
                dirs[:] = [d for d in dirs if not self._should_exclude(root_path / d)]
                for fname in files:
                    fpath = root_path / fname
                    if self._should_exclude(fpath):
                        continue
                    try:
                        stat = fpath.stat()
                        fp = FileFingerprint(
                            path=str(fpath),
                            sha256=self._compute_hash(fpath),
                            size=stat.st_size,
                            mtime=stat.st_mtime,
                            first_seen=time.time(),
                            last_verified=time.time(),
                        )
                        fingerprints[str(fpath)] = fp
                    except (PermissionError, FileNotFoundError):
                        continue
        except PermissionError:
            pass
        return fingerprints

    def initial_scan(self) -> Dict:
        now = time.time()
        total_files = 0
        for watch_dir in self.watch_dirs:
            if watch_dir.exists():
                found = self._scan_directory(watch_dir)
                self.fingerprints.update(found)
                total_files += len(found)
        self._save_state()
        return {
            "status": "SCAN_COMPLETE",
            "directories": len(self.watch_dirs),
            "total_files": total_files,
            "timestamp": now,
        }

    def check_integrity(self) -> Dict:
        now = time.time()
        changes: List[IntegrityEvent] = []
        current_files: Set[str] = set()

        for watch_dir in self.watch_dirs:
            if watch_dir.exists():
                for fpath_str in self._scan_directory(watch_dir):
                    current_files.add(fpath_str)

        for fpath_str, fp in list(self.fingerprints.items()):
            if fpath_str not in current_files:
                event = IntegrityEvent(
                    event_type="DELETED",
                    path=fpath_str,
                    old_hash=fp.sha256,
                    new_hash=None,
                    timestamp=now,
                    severity="HIGH",
                )
                changes.append(event)
                del self.fingerprints[fpath_str]
            else:
                try:
                    current_hash = self._compute_hash(Path(fpath_str))
                    if current_hash != fp.sha256:
                        event = IntegrityEvent(
                            event_type="MODIFIED",
                            path=fpath_str,
                            old_hash=fp.sha256,
                            new_hash=current_hash,
                            timestamp=now,
                            severity="CRITICAL",
                        )
                        changes.append(event)
                        self.fingerprints[fpath_str].sha256 = current_hash
                        self.fingerprints[fpath_str].last_verified = now
                except (FileNotFoundError, PermissionError):
                    pass

        for fpath_str in current_files:
            if fpath_str not in self.fingerprints:
                try:
                    fpath = Path(fpath_str)
                    stat = fpath.stat()
                    fp = FileFingerprint(
                        path=fpath_str,
                        sha256=self._compute_hash(fpath),
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        first_seen=now,
                        last_verified=now,
                    )
                    self.fingerprints[fpath_str] = fp
                    event = IntegrityEvent(
                        event_type="ADDED",
                        path=fpath_str,
                        old_hash=None,
                        new_hash=fp.sha256,
                        timestamp=now,
                        severity="MEDIUM",
                    )
                    changes.append(event)
                except (FileNotFoundError, PermissionError):
                    pass

        self.events.extend(changes)
        self._append_events(changes)
        self._save_state()

        return {
            "status": "CHECK_COMPLETE",
            "changes": len(changes),
            "events": [e.to_dict() for e in changes],
            "total_tracked": len(self.fingerprints),
            "timestamp": now,
        }

    def run_daemon(self):
        self.running = True
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        print(f"[OpenClaw] Watchdog started — monitoring {len(self.watch_dirs)} directories")
        print(f"[OpenClaw] Poll interval: {self.poll_interval}s")
        print(f"[OpenClaw] Tracking: {len(self.fingerprints)} files")

        while self.running:
            result = self.check_integrity()
            if result["changes"] > 0:
                print(f"[OpenClaw] {result['changes']} changes detected!")
                for event in result["events"]:
                    print(f"  [{event['severity']}] {event['event_type']}: {event['path']}")
            time.sleep(self.poll_interval)

    def _handle_signal(self, signum, frame):
        print("\n[OpenClaw] Shutting down watchdog...")
        self.running = False

    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "fingerprints": {k: v.to_dict() for k, v in self.fingerprints.items()},
            "last_scan": time.time(),
        }
        self.state_file.write_text(json.dumps(state, indent=2))

    def _load_state(self):
        if self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text())
                for k, v in state.get("fingerprints", {}).items():
                    self.fingerprints[k] = FileFingerprint.from_dict(v)
            except Exception:
                pass

    def _append_events(self, events: List[IntegrityEvent]):
        if not events:
            return
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.event_log, "a") as f:
            for event in events:
                f.write(json.dumps(event.to_dict()) + "\n")

    def get_report(self) -> Dict:
        return {
            "tracked_files": len(self.fingerprints),
            "total_events": len(self.events),
            "directories": [str(d) for d in self.watch_dirs],
            "recent_events": [e.to_dict() for e in self.events[-20:]],
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw Watchdog Daemon")
    parser.add_argument("--check", action="store_true", help="Run single integrity check")
    parser.add_argument("--scan", action="store_true", help="Run initial directory scan")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--dirs", nargs="+", default=["."], help="Directories to monitor")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds")
    parser.add_argument("--report", action="store_true", help="Show integrity report")
    args = parser.parse_args()

    daemon = WatchdogDaemon(
        watch_dirs=args.dirs,
        poll_interval=args.interval,
    )

    if args.scan:
        result = daemon.initial_scan()
        print(json.dumps(result, indent=2))
    elif args.check:
        result = daemon.check_integrity()
        print(json.dumps(result, indent=2))
    elif args.report:
        print(json.dumps(daemon.get_report(), indent=2))
    elif args.daemon:
        daemon.initial_scan()
        daemon.run_daemon()
    else:
        daemon.initial_scan()
        result = daemon.check_integrity()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
