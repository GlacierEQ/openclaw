"""Legacy test import path bound to the canonical integrity implementation."""
from src.integrity import FileFingerprint, IntegrityEvent, WatchdogDaemon

__all__ = ["FileFingerprint", "IntegrityEvent", "WatchdogDaemon"]
