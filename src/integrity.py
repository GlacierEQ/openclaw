from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import signal
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


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
    def from_dict(cls, value: Dict) -> "FileFingerprint":
        return cls(**value)


@dataclass
class IntegrityEvent:
    event_type: str
    path: str
    old_hash: Optional[str]
    new_hash: Optional[str]
    timestamp: float
    severity: str
    size: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class WatchdogDaemon:
    """Polling SHA-256 file-integrity monitor with persistent state.

    The daemon follows symlinks only when explicitly enabled and writes state
    atomically so an interrupted save cannot destroy the previous baseline.
    """

    def __init__(
        self,
        watch_dirs: List[str],
        state_file: str = ".openclaw/watchdog_state.json",
        event_log: str = ".openclaw/watchdog_events.jsonl",
        poll_interval: float = 2.0,
        exclude_patterns: Optional[List[str]] = None,
        *,
        follow_symlinks: bool = False,
    ):
        if not watch_dirs:
            raise ValueError("at least one watch directory is required")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        self.watch_dirs = [Path(d).expanduser().resolve() for d in watch_dirs]
        self.state_file = Path(state_file)
        self.event_log = Path(event_log)
        self.poll_interval = float(poll_interval)
        self.exclude_patterns = exclude_patterns or [
            ".git",
            "__pycache__",
            "node_modules",
            ".DS_Store",
            ".openclaw",
            "*.pyc",
            ".env",
        ]
        self.follow_symlinks = follow_symlinks
        self.fingerprints: Dict[str, FileFingerprint] = {}
        self.events: List[IntegrityEvent] = []
        self.running = False
        self._load_state()
        self._load_recent_events()

    def _should_exclude(self, path: Path) -> bool:
        parts = set(path.parts)
        text = str(path)
        for pattern in self.exclude_patterns:
            if pattern in parts:
                return True
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(text, pattern):
                return True
        return False

    @staticmethod
    def _compute_hash(filepath: Path) -> str:
        digest = hashlib.sha256()
        with filepath.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _fingerprint(self, path: Path, *, first_seen: Optional[float] = None) -> FileFingerprint:
        stat = path.stat()
        now = time.time()
        return FileFingerprint(
            path=str(path),
            sha256=self._compute_hash(path),
            size=stat.st_size,
            mtime=stat.st_mtime,
            first_seen=first_seen if first_seen is not None else now,
            last_verified=now,
        )

    def _scan_directory(self, directory: Path) -> Dict[str, FileFingerprint]:
        discovered: Dict[str, FileFingerprint] = {}
        if not directory.exists() or not directory.is_dir():
            return discovered
        for root, dirs, files in os.walk(directory, followlinks=self.follow_symlinks):
            root_path = Path(root)
            dirs[:] = [
                name
                for name in dirs
                if not self._should_exclude(root_path / name)
                and (self.follow_symlinks or not (root_path / name).is_symlink())
            ]
            for name in files:
                path = root_path / name
                if self._should_exclude(path):
                    continue
                if path.is_symlink() and not self.follow_symlinks:
                    continue
                try:
                    previous = self.fingerprints.get(str(path))
                    discovered[str(path)] = self._fingerprint(
                        path,
                        first_seen=previous.first_seen if previous else None,
                    )
                except (FileNotFoundError, PermissionError, OSError):
                    continue
        return discovered

    def _scan_all(self) -> Dict[str, FileFingerprint]:
        current: Dict[str, FileFingerprint] = {}
        for directory in self.watch_dirs:
            current.update(self._scan_directory(directory))
        return current

    def initial_scan(self) -> Dict:
        now = time.time()
        current = self._scan_all()
        self.fingerprints = current
        self._save_state()
        return {
            "status": "SCAN_COMPLETE",
            "directories": len(self.watch_dirs),
            "total_files": len(current),
            "timestamp": now,
        }

    def check_integrity(self) -> Dict:
        now = time.time()
        current = self._scan_all()
        changes: List[IntegrityEvent] = []
        old_paths: Set[str] = set(self.fingerprints)
        new_paths: Set[str] = set(current)

        for path in sorted(old_paths - new_paths):
            old = self.fingerprints[path]
            changes.append(
                IntegrityEvent("DELETED", path, old.sha256, None, now, "HIGH", old.size)
            )

        for path in sorted(new_paths - old_paths):
            new = current[path]
            changes.append(
                IntegrityEvent("ADDED", path, None, new.sha256, now, "MEDIUM", new.size)
            )

        for path in sorted(old_paths & new_paths):
            old = self.fingerprints[path]
            new = current[path]
            if old.sha256 != new.sha256:
                changes.append(
                    IntegrityEvent("MODIFIED", path, old.sha256, new.sha256, now, "CRITICAL", new.size)
                )
            else:
                new.first_seen = old.first_seen

        self.fingerprints = current
        self.events.extend(changes)
        self._append_events(changes)
        self._save_state()
        return {
            "status": "CHECK_COMPLETE",
            "changes": len(changes),
            "events": [event.to_dict() for event in changes],
            "total_tracked": len(self.fingerprints),
            "timestamp": now,
        }

    def run_daemon(self) -> None:
        self.running = True
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except ValueError:
            pass
        while self.running:
            self.check_integrity()
            time.sleep(self.poll_interval)

    def _handle_signal(self, signum, frame) -> None:
        self.running = False

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "openclaw.integrity-state.v1",
            "fingerprints": {k: v.to_dict() for k, v in self.fingerprints.items()},
            "last_scan": time.time(),
        }
        temp_fd, temp_name = tempfile.mkstemp(
            prefix=self.state_file.name + ".",
            dir=str(self.state_file.parent),
            text=True,
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.state_file)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _load_state(self) -> None:
        if not self.state_file.exists():
            return
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.fingerprints = {
                path: FileFingerprint.from_dict(value)
                for path, value in payload.get("fingerprints", {}).items()
            }
        except (OSError, ValueError, TypeError):
            self.fingerprints = {}

    def _append_events(self, events: Iterable[IntegrityEvent]) -> None:
        events = list(events)
        if not events:
            return
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _load_recent_events(self, limit: int = 200) -> None:
        if not self.event_log.exists():
            return
        try:
            lines = self.event_log.read_text(encoding="utf-8").splitlines()[-limit:]
            self.events = [IntegrityEvent(**json.loads(line)) for line in lines if line.strip()]
        except (OSError, ValueError, TypeError):
            self.events = []

    def get_report(self) -> Dict:
        return {
            "tracked_files": len(self.fingerprints),
            "total_events": len(self.events),
            "directories": [str(path) for path in self.watch_dirs],
            "recent_events": [event.to_dict() for event in self.events[-20:]],
            "state_file": str(self.state_file),
            "event_log": str(self.event_log),
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OpenClaw file integrity watchdog")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--dirs", nargs="+", default=["."])
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    daemon = WatchdogDaemon(args.dirs, poll_interval=args.interval)
    if args.scan:
        result = daemon.initial_scan()
    elif args.check:
        result = daemon.check_integrity()
    elif args.report:
        result = daemon.get_report()
    elif args.daemon:
        daemon.initial_scan()
        daemon.run_daemon()
        return
    else:
        daemon.initial_scan()
        result = daemon.check_integrity()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
