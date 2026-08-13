#!/usr/bin/env python3
"""Compatibility entry point for the OpenClaw integrity daemon."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.integrity import FileFingerprint, IntegrityEvent, WatchdogDaemon, main

__all__ = ["FileFingerprint", "IntegrityEvent", "WatchdogDaemon", "main"]

if __name__ == "__main__":
    main()
