#!/usr/bin/env python3
"""Cloud storage bridges for OpenClaw mesh state.

Secrets are runtime inputs. They are never persisted in the OpenClaw cloud
configuration file. Durable configuration stores only provider names, target
locations, and environment-variable references.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PATH_LENGTH = 1024
RATE_LIMIT_WINDOW = 60.0
MAX_REQUESTS_PER_WINDOW = 50
DEFAULT_SECRET_ENVS = {
    "dropbox": "DROPBOX_ACCESS_TOKEN",
    "github": "GITHUB_TOKEN",
}


class RateLimiter:
    def __init__(self, max_requests: int = MAX_REQUESTS_PER_WINDOW, window: float = RATE_LIMIT_WINDOW):
        if max_requests <= 0 or window <= 0:
            raise ValueError("rate limit values must be positive")
        self.max_requests = int(max_requests)
        self.window = float(window)
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else float(now)
        with self._lock:
            cutoff = current - self.window
            self.requests[key] = [stamp for stamp in self.requests[key] if stamp > cutoff]
            if len(self.requests[key]) >= self.max_requests:
                return False
            self.requests[key].append(current)
            return True


class InputValidator:
    @staticmethod
    def validate_path(path: str) -> bool:
        if not isinstance(path, str) or not path or len(path) > MAX_PATH_LENGTH:
            return False
        normalized = path.replace("\\", "/")
        return ".." not in normalized.split("/")

    @staticmethod
    def validate_token(token: str) -> bool:
        return isinstance(token, str) and 10 <= len(token) <= 4096 and "\n" not in token and "\r" not in token

    @staticmethod
    def validate_data_size(data: Any) -> bool:
        try:
            return len(json.dumps(data, separators=(",", ":"), default=str).encode("utf-8")) <= MAX_FILE_SIZE
        except Exception:
            return False


class CloudError(RuntimeError):
    pass


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: float = 20.0,
) -> Any:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise CloudError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CloudError(f"network error: {exc.reason}") from exc


class DropboxBridge:
    API_BASE = "https://api.dropboxapi.com"
    CONTENT_BASE = "https://content.dropboxapi.com"

    def __init__(self, access_token: str):
        if not InputValidator.validate_token(access_token):
            raise ValueError("invalid Dropbox token")
        self.access_token = access_token
        self.connected = False
        self.account_id: Optional[str] = None
        self.rate_limiter = RateLimiter(30, 60)

    def _headers(self, *, content_type: str = "application/json") -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
            "User-Agent": "GlacierEQ-OpenClaw/3.1",
        }

    def connect(self) -> bool:
        try:
            data = _request_json(
                f"{self.API_BASE}/2/users/get_current_account",
                method="POST",
                headers=self._headers(),
                body=b"null",
                timeout=10,
            )
            self.account_id = data.get("account_id") if isinstance(data, dict) else None
            self.connected = bool(self.account_id)
        except CloudError:
            self.connected = False
        return self.connected

    def upload(self, path: str, data: Dict[str, Any]) -> bool:
        if not self.connected or not InputValidator.validate_path(path) or not InputValidator.validate_data_size(data):
            return False
        if not self.rate_limiter.is_allowed("upload"):
            return False
        payload = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
        headers = self._headers(content_type="application/octet-stream")
        headers["Dropbox-API-Arg"] = json.dumps({"path": path, "mode": "overwrite", "autorename": False})
        try:
            _request_json(f"{self.CONTENT_BASE}/2/files/upload", method="POST", headers=headers, body=payload, timeout=30)
            return True
        except CloudError:
            return False

    def download(self, path: str) -> Optional[Dict[str, Any]]:
        if not self.connected or not InputValidator.validate_path(path) or not self.rate_limiter.is_allowed("download"):
            return None
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Dropbox-API-Arg": json.dumps({"path": path}),
            "User-Agent": "GlacierEQ-OpenClaw/3.1",
        }
        request = urllib.request.Request(f"{self.CONTENT_BASE}/2/files/download", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
            return None


class GitHubBridge:
    API_BASE = "https://api.github.com"

    def __init__(self, token: str):
        if not InputValidator.validate_token(token):
            raise ValueError("invalid GitHub token")
        self.token = token
        self.username: Optional[str] = None
        self.connected = False
        self.rate_limiter = RateLimiter(30, 60)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GlacierEQ-OpenClaw/3.1",
        }

    def connect(self) -> bool:
        try:
            data = _request_json(f"{self.API_BASE}/user", headers=self._headers(), timeout=10)
            self.username = data.get("login") if isinstance(data, dict) else None
            self.connected = bool(self.username)
        except CloudError:
            self.connected = False
        return self.connected

    def _repo_full_name(self, repo: str) -> Optional[str]:
        if not InputValidator.validate_path(repo):
            return None
        if "/" in repo:
            owner, name = repo.split("/", 1)
            return f"{owner}/{name}" if owner and name else None
        return f"{self.username}/{repo}" if self.username else None

    def upload_file(self, repo: str, path: str, content: Dict[str, Any], message: str = "Update OpenClaw mesh state") -> bool:
        if not self.connected or not InputValidator.validate_path(path) or not InputValidator.validate_data_size(content):
            return False
        full_name = self._repo_full_name(repo)
        if not full_name or not self.rate_limiter.is_allowed("upload"):
            return False
        quoted_path = "/".join(urllib.parse.quote(part, safe="") for part in path.strip("/").split("/"))
        url = f"{self.API_BASE}/repos/{full_name}/contents/{quoted_path}"
        sha: Optional[str] = None
        try:
            existing = _request_json(url, headers=self._headers(), timeout=10)
            if isinstance(existing, dict):
                sha = existing.get("sha")
        except CloudError:
            pass
        payload: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(json.dumps(content, indent=2, sort_keys=True).encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        try:
            _request_json(url, method="PUT", headers=headers, body=json.dumps(payload).encode("utf-8"), timeout=30)
            return True
        except CloudError:
            return False

    def download_file(self, repo: str, path: str) -> Optional[Dict[str, Any]]:
        if not self.connected or not InputValidator.validate_path(path) or not self.rate_limiter.is_allowed("download"):
            return None
        full_name = self._repo_full_name(repo)
        if not full_name:
            return None
        quoted_path = "/".join(urllib.parse.quote(part, safe="") for part in path.strip("/").split("/"))
        try:
            data = _request_json(f"{self.API_BASE}/repos/{full_name}/contents/{quoted_path}", headers=self._headers(), timeout=10)
            encoded = data.get("content", "") if isinstance(data, dict) else ""
            return json.loads(base64.b64decode(encoded).decode("utf-8")) if encoded else None
        except (CloudError, ValueError, TypeError):
            return None


class CloudStorageManager:
    """Provider manager with metadata-only durable configuration."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or "~/.glaciereq/mesh/cloud.json").expanduser()
        self.configs: Dict[str, Dict[str, Any]] = {}
        self.bridges: Dict[str, Any] = {}
        self._runtime_secrets: Dict[str, str] = {}
        self._load_config()
        self._build_bridges_from_environment()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            return
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.configs = value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            self.configs = {}

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.config_path.name + ".", dir=str(self.config_path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.configs, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.config_path)
            os.chmod(self.config_path, 0o600)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _credential_for(self, provider: str) -> Optional[str]:
        if provider in self._runtime_secrets:
            return self._runtime_secrets[provider]
        env_name = str(self.configs.get(provider, {}).get("credential_env") or DEFAULT_SECRET_ENVS.get(provider, ""))
        return os.getenv(env_name) if env_name else None

    def _make_bridge(self, provider: str, secret: str):
        if provider == "dropbox":
            return DropboxBridge(secret)
        if provider == "github":
            return GitHubBridge(secret)
        raise ValueError(f"unsupported provider: {provider}")

    def _build_bridges_from_environment(self) -> None:
        for provider, config in self.configs.items():
            if not config.get("enabled", True):
                continue
            secret = self._credential_for(provider)
            if secret and InputValidator.validate_token(secret):
                self.bridges[provider] = self._make_bridge(provider, secret)

    def configure_provider(
        self,
        provider: str,
        *,
        credential_env: Optional[str] = None,
        target: Optional[Dict[str, str]] = None,
        enabled: bool = True,
    ) -> bool:
        if provider not in DEFAULT_SECRET_ENVS:
            return False
        env_name = credential_env or DEFAULT_SECRET_ENVS[provider]
        if not env_name or not env_name.replace("_", "").isalnum():
            return False
        self.configs[provider] = {
            "enabled": bool(enabled),
            "credential_env": env_name,
            "target": dict(target or {}),
            "last_sync": self.configs.get(provider, {}).get("last_sync", 0),
        }
        self._save_config()
        secret = os.getenv(env_name)
        if secret and InputValidator.validate_token(secret):
            self.bridges[provider] = self._make_bridge(provider, secret)
        else:
            self.bridges.pop(provider, None)
        return True

    def add_provider(self, provider: str, credentials: Dict[str, str], target: Optional[Dict[str, str]] = None) -> bool:
        """Compatibility helper. Credentials are memory-only and are never written to disk."""
        if provider not in DEFAULT_SECRET_ENVS:
            return False
        key = "access_token" if provider == "dropbox" else "token"
        secret = credentials.get(key, "")
        if not InputValidator.validate_token(secret):
            return False
        self._runtime_secrets[provider] = secret
        self.bridges[provider] = self._make_bridge(provider, secret)
        if provider not in self.configs:
            self.configs[provider] = {
                "enabled": True,
                "credential_env": DEFAULT_SECRET_ENVS[provider],
                "target": dict(target or {}),
                "last_sync": 0,
            }
        elif target is not None:
            self.configs[provider]["target"] = dict(target)
        self._save_config()
        return True

    def connect_all(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for provider, config in self.configs.items():
            if not config.get("enabled", True):
                continue
            bridge = self.bridges.get(provider)
            if bridge is None:
                secret = self._credential_for(provider)
                if secret and InputValidator.validate_token(secret):
                    bridge = self._make_bridge(provider, secret)
                    self.bridges[provider] = bridge
            results[provider] = bool(bridge and bridge.connect())
        return results

    def sync_knowledge(self, knowledge: Dict[str, Any]) -> Dict[str, bool]:
        """Write one mesh snapshot to every connected, explicitly targeted provider."""
        if not InputValidator.validate_data_size(knowledge):
            return {provider: False for provider in self.configs}
        results: Dict[str, bool] = {}
        for provider, config in self.configs.items():
            bridge = self.bridges.get(provider)
            target = config.get("target", {})
            if provider == "dropbox":
                path = str(target.get("path", "/GlacierEQ/Mesh/knowledge.json"))
                results[provider] = bool(bridge and bridge.connected and bridge.upload(path, knowledge))
            elif provider == "github":
                repo = str(target.get("repo", ""))
                path = str(target.get("path", "mesh/knowledge.json"))
                results[provider] = bool(bridge and bridge.connected and repo and bridge.upload_file(repo, path, knowledge))
            else:
                results[provider] = False
            if results[provider]:
                config["last_sync"] = time.time()
        self._save_config()
        return results

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            provider: {
                "enabled": config.get("enabled", True),
                "credential_env": config.get("credential_env"),
                "credential_available": bool(self._credential_for(provider)),
                "connected": bool(getattr(self.bridges.get(provider), "connected", False)),
                "target": config.get("target", {}),
                "last_sync": config.get("last_sync", 0),
            }
            for provider, config in self.configs.items()
        }


def create_cloud_manager(config_path: Optional[str] = None, master_key: Optional[str] = None) -> CloudStorageManager:
    # master_key is retained only for call-site compatibility; secrets are no longer persisted.
    return CloudStorageManager(config_path)
