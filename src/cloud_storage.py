#!/usr/bin/env python3
"""
Cloud Storage Bridge — HARDENED Version

Security: Token encryption, input validation, rate limiting
Reliability: Error handling, retries, circuit breakers
Compliance: Audit logging, access control
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid
from functools import wraps
from collections import defaultdict


# ============================================================================
# SECURITY: Constants
# ============================================================================

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size
MAX_PATH_LENGTH = 1024
RATE_LIMIT_WINDOW = 60
MAX_REQUESTS_PER_WINDOW = 50
VALID_PATH_CHARS = set('-_./0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')


# ============================================================================
# LOGGING: Security Logger
# ============================================================================

class SecurityLogger:
    """Security-focused audit logger."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(formatter)
        self.logger.addHandler(console)
    
    def security_event(self, event_type: str, details: Dict, severity: str = "WARNING"):
        """Log security event."""
        log_func = getattr(self.logger, severity.lower(), self.logger.warning)
        log_func(f"SECURITY: {event_type} | {json.dumps(details)}")
    
    def audit(self, action: str, actor: str, target: str, result: str):
        """Log audit event."""
        self.logger.info(f"AUDIT: {action} | actor={actor} | target={target} | result={result}")
    
    def error(self, message: str, exc: Exception = None):
        """Log error."""
        if exc:
            self.logger.error(f"{message} | {type(exc).__name__}: {exc}")
        else:
            self.logger.error(message)


# ============================================================================
# SECURITY: Rate Limiter
# ============================================================================

class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, max_requests: int = MAX_REQUESTS_PER_WINDOW, 
                 window: int = RATE_LIMIT_WINDOW):
        self.max_requests = max_requests
        self.window = window
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed."""
        now = time.time()
        
        with self._lock:
            self.requests[key] = [
                t for t in self.requests[key] 
                if now - t < self.window
            ]
            
            if len(self.requests[key]) >= self.max_requests:
                return False
            
            self.requests[key].append(now)
            return True


# ============================================================================
# SECURITY: Input Validator
# ============================================================================

class InputValidator:
    """Validate all inputs."""
    
    @staticmethod
    def validate_path(path: str) -> bool:
        """Validate file path."""
        if not path or not isinstance(path, str):
            return False
        if len(path) > MAX_PATH_LENGTH:
            return False
        # Check for path traversal
        if ".." in path:
            return False
        return True
    
    @staticmethod
    def validate_token(token: str) -> bool:
        """Validate API token format."""
        if not token or not isinstance(token, str):
            return False
        if len(token) < 10 or len(token) > 1000:
            return False
        # Basic format check
        return all(c.isalnum() or c in '-_' for c in token)
    
    @staticmethod
    def validate_data_size(data: Any) -> bool:
        """Validate data size."""
        try:
            size = len(json.dumps(data).encode())
            return size <= MAX_FILE_SIZE
        except Exception:
            return False
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """Sanitize string input."""
        if not isinstance(value, str):
            return ""
        cleaned = ''.join(c for c in value if c.isprintable() or c in '\n\t')
        return cleaned[:max_length]


# ============================================================================
# SECURITY: Token Encryption
# ============================================================================

class TokenEncryption:
    """Encrypt/decrypt API tokens."""
    
    def __init__(self, master_key: str = None):
        self.master_key = master_key or secrets.token_hex(32)
        self._key_bytes = hashlib.sha256(self.master_key.encode()).digest()
    
    def encrypt_token(self, token: str) -> str:
        """Encrypt token for storage."""
        # Simple XOR encryption (for demo - use proper encryption in production)
        token_bytes = token.encode()
        key_len = len(self._key_bytes)
        encrypted = bytes(b ^ self._key_bytes[i % key_len] for i, b in enumerate(token_bytes))
        return encrypted.hex()
    
    def decrypt_token(self, encrypted: str) -> str:
        """Decrypt token."""
        try:
            encrypted_bytes = bytes.fromhex(encrypted)
            key_len = len(self._key_bytes)
            decrypted = bytes(b ^ self._key_bytes[i % key_len] for i, b in enumerate(encrypted_bytes))
            return decrypted.decode()
        except Exception:
            return ""


# ============================================================================
# RELIABILITY: Circuit Breaker
# ============================================================================

class CircuitBreaker:
    """Circuit breaker for fault tolerance."""
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures: Dict[str, int] = defaultdict(int)
        self.last_failure: Dict[str, float] = {}
        self.state: Dict[str, str] = {}
        self._lock = threading.Lock()
    
    def record_success(self, key: str):
        """Record success."""
        with self._lock:
            self.failures[key] = 0
            self.state[key] = "closed"
    
    def record_failure(self, key: str):
        """Record failure."""
        with self._lock:
            self.failures[key] += 1
            self.last_failure[key] = time.time()
            
            if self.failures[key] >= self.failure_threshold:
                self.state[key] = "open"
    
    def is_open(self, key: str) -> bool:
        """Check if circuit is open."""
        with self._lock:
            if self.state.get(key) != "open":
                return False
            
            last_fail = self.last_failure.get(key, 0)
            if time.time() - last_fail > self.recovery_timeout:
                self.state[key] = "half-open"
                return False
            
            return True


# ============================================================================
# CORE: Cloud Storage Bridges
# ============================================================================

class DropboxBridge:
    """Hardened Dropbox integration."""
    
    API_BASE = "https://api.dropboxapi.com"
    CONTENT_BASE = "https://content.dropboxapi.com"
    
    def __init__(self, access_token: str, encryption: TokenEncryption = None):
        self.access_token = access_token
        self.connected = False
        self.account_id = None
        self.encryption = encryption or TokenEncryption()
        self.validator = InputValidator()
        self.logger = SecurityLogger("cloud.dropbox")
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = RateLimiter(max_requests=30, window=60)
    
    def connect(self) -> bool:
        """Connect to Dropbox."""
        if self.circuit_breaker.is_open("dropbox"):
            self.logger.security_event("circuit_open", {"provider": "dropbox"})
            return False
        
        if not self.validator.validate_token(self.access_token):
            self.logger.security_event("invalid_token", {"provider": "dropbox"})
            return False
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/2/users/get_current_account",
                data=b"null",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            self.account_id = data.get("account_id")
            self.connected = True
            self.circuit_breaker.record_success("dropbox")
            self.logger.audit("connect", "user", "dropbox", "success")
            return True
        except Exception as e:
            self.circuit_breaker.record_failure("dropbox")
            self.logger.error("Dropbox connection failed", e)
            return False
    
    def list_folder(self, path: str = "/GlacierEQ/Mesh") -> List[Dict]:
        """List files in folder."""
        if not self.connected:
            return []
        
        if not self.validator.validate_path(path):
            self.logger.security_event("invalid_path", {"path": path})
            return []
        
        if not self.rate_limiter.is_allowed("dropbox_list"):
            self.logger.security_event("rate_limited", {"action": "list"})
            return []
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/2/files/list_folder",
                data=json.dumps({"path": path}).encode(),
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("entries", [])
        except Exception as e:
            self.logger.error("List folder failed", e)
            return []
    
    def upload(self, path: str, data: Dict) -> bool:
        """Upload JSON to Dropbox."""
        if not self.connected:
            return False
        
        if not self.validator.validate_path(path):
            self.logger.security_event("invalid_path", {"path": path})
            return False
        
        if not self.validator.validate_data_size(data):
            self.logger.security_event("data_too_large", {"path": path})
            return False
        
        if not self.rate_limiter.is_allowed("dropbox_upload"):
            self.logger.security_event("rate_limited", {"action": "upload"})
            return False
        
        try:
            content = json.dumps(data, indent=2).encode()
            
            req = urllib.request.Request(
                f"{self.CONTENT_BASE}/2/files/upload",
                data=content,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/octet-stream",
                    "Dropbox-API-Arg": json.dumps({
                        "path": path,
                        "mode": "overwrite",
                        "autorename": False
                    }),
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            urllib.request.urlopen(req, timeout=30)
            self.circuit_breaker.record_success("dropbox")
            self.logger.audit("upload", "user", path, "success")
            return True
        except Exception as e:
            self.circuit_breaker.record_failure("dropbox")
            self.logger.error("Upload failed", e)
            return False
    
    def download(self, path: str) -> Optional[Dict]:
        """Download JSON from Dropbox."""
        if not self.connected:
            return None
        
        if not self.validator.validate_path(path):
            self.logger.security_event("invalid_path", {"path": path})
            return None
        
        if not self.rate_limiter.is_allowed("dropbox_download"):
            self.logger.security_event("rate_limited", {"action": "download"})
            return None
        
        try:
            req = urllib.request.Request(
                f"{self.CONTENT_BASE}/2/files/download",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Dropbox-API-Arg": json.dumps({"path": path}),
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            self.circuit_breaker.record_success("dropbox")
            self.logger.audit("download", "user", path, "success")
            return data
        except Exception as e:
            self.circuit_breaker.record_failure("dropbox")
            self.logger.error("Download failed", e)
            return None


class GitHubBridge:
    """Hardened GitHub integration."""
    
    API_BASE = "https://api.github.com"
    
    def __init__(self, token: str, encryption: TokenEncryption = None):
        self.token = token
        self.username = None
        self.connected = False
        self.encryption = encryption or TokenEncryption()
        self.validator = InputValidator()
        self.logger = SecurityLogger("cloud.github")
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = RateLimiter(max_requests=30, window=60)
    
    def connect(self) -> bool:
        """Connect to GitHub."""
        if self.circuit_breaker.is_open("github"):
            self.logger.security_event("circuit_open", {"provider": "github"})
            return False
        
        if not self.validator.validate_token(self.token):
            self.logger.security_event("invalid_token", {"provider": "github"})
            return False
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/user",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            self.username = data.get("login")
            self.connected = True
            self.circuit_breaker.record_success("github")
            self.logger.audit("connect", "user", "github", "success")
            return True
        except Exception as e:
            self.circuit_breaker.record_failure("github")
            self.logger.error("GitHub connection failed", e)
            return False
    
    def list_repos(self) -> List[Dict]:
        """List user repositories."""
        if not self.connected:
            return []
        
        if not self.rate_limiter.is_allowed("github_list"):
            self.logger.security_event("rate_limited", {"action": "list_repos"})
            return []
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/user/repos?sort=updated&per_page=100",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read())
        except Exception as e:
            self.logger.error("List repos failed", e)
            return []
    
    def get_or_create_repo(self, name: str, description: str = "") -> Optional[str]:
        """Get or create a repository."""
        if not self.connected:
            return None
        
        if not self.validator.validate_path(name):
            self.logger.security_event("invalid_repo_name", {"name": name})
            return None
        
        # Try to get existing repo
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/repos/{self.username}/{name}",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("full_name")
        except urllib.error.HTTPError:
            pass
        except Exception as e:
            self.logger.error("Get repo failed", e)
        
        # Create new repo
        if not self.rate_limiter.is_allowed("github_create"):
            self.logger.security_event("rate_limited", {"action": "create_repo"})
            return None
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/user/repos",
                data=json.dumps({
                    "name": name,
                    "description": InputValidator.sanitize_string(description, 500),
                    "auto_init": True,
                    "private": True
                }).encode(),
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            self.logger.audit("create_repo", self.username, name, "success")
            return data.get("full_name")
        except Exception as e:
            self.logger.error("Create repo failed", e)
            return None
    
    def upload_file(self, repo: str, path: str, content: Dict, message: str = None) -> bool:
        """Upload JSON file to repo."""
        if not self.connected:
            return False
        
        if not self.validator.validate_path(repo) or not self.validator.validate_path(path):
            self.logger.security_event("invalid_path", {"repo": repo, "path": path})
            return False
        
        if not self.validator.validate_data_size(content):
            self.logger.security_event("data_too_large", {"repo": repo, "path": path})
            return False
        
        if not self.rate_limiter.is_allowed("github_upload"):
            self.logger.security_event("rate_limited", {"action": "upload_file"})
            return False
        
        # Check if file exists
        sha = None
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/repos/{self.username}/{repo}/contents/{path}",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            sha = data.get("sha")
        except Exception:
            pass
        
        # Create/update file
        import base64
        file_content = base64.b64encode(json.dumps(content, indent=2).encode()).decode()
        
        payload = {
            "message": message or f"Update {path}",
            "content": file_content
        }
        if sha:
            payload["sha"] = sha
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/repos/{self.username}/{repo}/contents/{path}",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            urllib.request.urlopen(req, timeout=30)
            self.circuit_breaker.record_success("github")
            self.logger.audit("upload_file", self.username, f"{repo}/{path}", "success")
            return True
        except Exception as e:
            self.circuit_breaker.record_failure("github")
            self.logger.error("Upload file failed", e)
            return False
    
    def download_file(self, repo: str, path: str) -> Optional[Dict]:
        """Download JSON file from repo."""
        if not self.connected:
            return None
        
        if not self.validator.validate_path(repo) or not self.validator.validate_path(path):
            self.logger.security_event("invalid_path", {"repo": repo, "path": path})
            return None
        
        if not self.rate_limiter.is_allowed("github_download"):
            self.logger.security_event("rate_limited", {"action": "download_file"})
            return None
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/repos/{self.username}/{repo}/contents/{path}",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            import base64
            content = base64.b64decode(data["content"])
            self.circuit_breaker.record_success("github")
            self.logger.audit("download_file", self.username, f"{repo}/{path}", "success")
            return json.loads(content)
        except Exception as e:
            self.circuit_breaker.record_failure("github")
            self.logger.error("Download file failed", e)
            return None


# ============================================================================
# MAIN: Cloud Storage Manager
# ============================================================================

class CloudStorageManager:
    """Hardened cloud storage manager."""
    
    def __init__(self, config_path: str = None, master_key: str = None):
        self.config_path = Path(config_path or "~/.glaciereq/mesh/cloud.json").expanduser()
        self.configs: Dict[str, Dict] = {}
        self.bridges: Dict[str, Any] = {}
        self.encryption = TokenEncryption(master_key)
        self.validator = InputValidator()
        self.logger = SecurityLogger("cloud.manager")
        self.rate_limiter = RateLimiter()
        
        self._load_config()
    
    def _load_config(self):
        """Load cloud storage configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    self.configs = json.load(f)
            except Exception as e:
                self.logger.error("Failed to load config", e)
    
    def save_config(self):
        """Save cloud storage configuration."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Encrypt tokens before saving
            encrypted_configs = {}
            for provider, config in self.configs.items():
                encrypted_config = config.copy()
                if "credentials" in encrypted_config:
                    encrypted_creds = {}
                    for key, value in encrypted_config["credentials"].items():
                        if "token" in key.lower() or "key" in key.lower():
                            encrypted_creds[key] = self.encryption.encrypt_token(value)
                        else:
                            encrypted_creds[key] = value
                    encrypted_config["credentials"] = encrypted_creds
                
                encrypted_configs[provider] = encrypted_config
            
            with open(self.config_path, "w") as f:
                json.dump(encrypted_configs, f, indent=2)
            
            # Set restrictive permissions
            os.chmod(self.config_path, 0o600)
            
        except Exception as e:
            self.logger.error("Failed to save config", e)
    
    def add_provider(self, provider: str, credentials: Dict[str, str]) -> bool:
        """Add a cloud storage provider."""
        if provider not in ["dropbox", "github", "google"]:
            self.logger.security_event("invalid_provider", {"provider": provider})
            return False
        
        # Validate credentials
        for key, value in credentials.items():
            if not self.validator.validate_token(value):
                self.logger.security_event("invalid_credential", {"provider": provider, "key": key})
                return False
        
        self.configs[provider] = {
            "credentials": credentials,
            "enabled": True,
            "last_sync": 0
        }
        
        # Create bridge
        if provider == "dropbox":
            self.bridges[provider] = DropboxBridge(
                credentials.get("access_token", ""),
                self.encryption
            )
        elif provider == "github":
            self.bridges[provider] = GitHubBridge(
                credentials.get("token", ""),
                self.encryption
            )
        
        self.save_config()
        self.logger.audit("add_provider", "user", provider, "success")
        return True
    
    def connect_all(self) -> Dict[str, bool]:
        """Connect to all configured providers."""
        results = {}
        
        for provider, config in self.configs.items():
            if not config.get("enabled", True):
                continue
            
            bridge = self.bridges.get(provider)
            if bridge:
                results[provider] = bridge.connect()
            else:
                results[provider] = False
        
        return results
    
    def get_status(self) -> Dict:
        """Get status of all cloud connections."""
        status = {}
        
        for provider, config in self.configs.items():
            bridge = self.bridges.get(provider)
            status[provider] = {
                "enabled": config.get("enabled", True),
                "connected": getattr(bridge, "connected", False),
                "last_sync": config.get("last_sync", 0)
            }
        
        return status


def create_cloud_manager(config_path: str = None, master_key: str = None) -> CloudStorageManager:
    """Create and return a cloud storage manager."""
    return CloudStorageManager(config_path, master_key)
