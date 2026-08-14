"""Canonical OpenClaw runtime version."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "glaciereq-openclaw"
SOURCE_VERSION = "3.2.0"

try:
    __version__ = version(PACKAGE_NAME)
except PackageNotFoundError:
    __version__ = SOURCE_VERSION

VERSION = __version__

__all__ = ["PACKAGE_NAME", "SOURCE_VERSION", "VERSION", "__version__"]
