#!/usr/bin/env python3
"""
Cloud Storage Bridge — Dropbox, Google Drive, GitHub as Knowledge Layers

Philosophy: Intelligence can come from surprising places.
            Your Dropbox, your Google Drive, your GitHub repos —
            they're all potential sources of distributed knowledge.

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │              CLOUD STORAGE BRIDGE                    │
    ├─────────────────────────────────────────────────────┤
    │  DROPBOX    →  File sync, shared folders             │
    │  GOOGLE     →  Drive, Docs, Sheets                   │
    │  GITHUB     →  Repos, Gists, Issues                  │
    │  ICLOUD     →  Apple ecosystem                       │
    │  ONEDRIVE   →  Microsoft ecosystem                   │
    │  GDRIVE     →  Generic WebDAV                        │
    └─────────────────────────────────────────────────────┘
"""

import hashlib
import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid


class StorageProvider(Enum):
    """Cloud storage providers."""
    DROPBOX = "dropbox"
    GOOGLE_DRIVE = "google_drive"
    GITHUB = "github"
    ICLOUD = "icloud"
    ONEDRIVE = "onedrive"
    GDRIVE = "gdrive"  # Generic WebDAV


@dataclass
class StorageConfig:
    """Configuration for a storage provider."""
    provider: StorageProvider
    credentials: Dict[str, str]
    sync_interval: float = 300.0  # seconds
    enabled: bool = True
    last_sync: float = 0.0
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        return d


@dataclass
class SyncEntry:
    """An entry in the sync store."""
    entry_id: str
    path: str
    data: Dict[str, Any]
    timestamp: float
    version: int = 1
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(json.dumps(self.data, sort_keys=True).encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict:
        return asdict(self)


class DropboxBridge:
    """Dropbox integration for mesh knowledge."""
    
    API_BASE = "https://api.dropboxapi.com"
    CONTENT_BASE = "https://content.dropboxapi.com"
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.connected = False
        self.account_id = None
    
    def connect(self) -> bool:
        """Connect to Dropbox."""
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/2/users/get_current_account",
                data=b"null",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            self.account_id = data.get("account_id")
            self.connected = True
            return True
        except Exception as e:
            print(f"[Dropbox] Connection failed: {e}")
            return False
    
    def list_folder(self, path: str = "/GlacierEQ/Mesh") -> List[Dict]:
        """List files in folder."""
        if not self.connected:
            return []
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/2/files/list_folder",
                data=json.dumps({"path": path}).encode(),
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("entries", [])
        except Exception:
            return []
    
    def upload(self, path: str, data: Dict) -> bool:
        """Upload JSON to Dropbox."""
        if not self.connected:
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
                    })
                }
            )
            urllib.request.urlopen(req, timeout=30)
            return True
        except Exception as e:
            print(f"[Dropbox] Upload failed: {e}")
            return False
    
    def download(self, path: str) -> Optional[Dict]:
        """Download JSON from Dropbox."""
        if not self.connected:
            return None
        
        try:
            req = urllib.request.Request(
                f"{self.CONTENT_BASE}/2/files/download",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Dropbox-API-Arg": json.dumps({"path": path})
                }
            )
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except Exception:
            return None
    
    def create_shared_link(self, path: str) -> Optional[str]:
        """Create a shared link for a file."""
        if not self.connected:
            return None
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/2/sharing/create_shared_link_with_settings",
                data=json.dumps({"path": path}).encode(),
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("url")
        except Exception:
            return None


class GoogleDriveBridge:
    """Google Drive integration for mesh knowledge."""
    
    API_BASE = "https://www.googleapis.com/drive/v3"
    UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
    
    def __init__(self, credentials: Dict[str, str]):
        self.credentials = credentials
        self.access_token = credentials.get("access_token", "")
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to Google Drive."""
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/about?fields=user",
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            self.connected = True
            return True
        except Exception as e:
            print(f"[Google Drive] Connection failed: {e}")
            return False
    
    def list_files(self, folder_id: str = None) -> List[Dict]:
        """List files in folder."""
        if not self.connected:
            return []
        
        try:
            query = f"'{folder_id}' in parents" if folder_id else ""
            req = urllib.request.Request(
                f"{self.API_BASE}/files?q={query}&fields=files(id,name,mimeType,modifiedTime)",
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("files", [])
        except Exception:
            return []
    
    def upload(self, name: str, data: Dict, folder_id: str = None) -> bool:
        """Upload JSON to Google Drive."""
        if not self.connected:
            return False
        
        try:
            content = json.dumps(data, indent=2).encode()
            
            metadata = {"name": name, "mimeType": "application/json"}
            if folder_id:
                metadata["parents"] = [folder_id]
            
            # Create file
            req = urllib.request.Request(
                f"{self.UPLOAD_BASE}/files?uploadType=multipart",
                data=content,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json"
                }
            )
            urllib.request.urlopen(req, timeout=30)
            return True
        except Exception as e:
            print(f"[Google Drive] Upload failed: {e}")
            return False
    
    def download(self, file_id: str) -> Optional[Dict]:
        """Download JSON from Google Drive."""
        if not self.connected:
            return None
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/files/{file_id}?alt=media",
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                }
            )
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except Exception:
            return None


class GitHubBridge:
    """GitHub integration for mesh knowledge."""
    
    API_BASE = "https://api.github.com"
    
    def __init__(self, token: str):
        self.token = token
        self.username = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to GitHub."""
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/user",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            self.username = data.get("login")
            self.connected = True
            return True
        except Exception as e:
            print(f"[GitHub] Connection failed: {e}")
            return False
    
    def list_repos(self) -> List[Dict]:
        """List user repositories."""
        if not self.connected:
            return []
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/user/repos?sort=updated&per_page=100",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read())
        except Exception:
            return []
    
    def get_or_create_repo(self, name: str, description: str = "") -> Optional[str]:
        """Get or create a repository."""
        if not self.connected:
            return None
        
        # Try to get existing repo
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/repos/{self.username}/{name}",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("full_name")
        except urllib.error.HTTPError:
            pass
        
        # Create new repo
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/user/repos",
                data=json.dumps({
                    "name": name,
                    "description": description,
                    "auto_init": True,
                    "private": True
                }).encode(),
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Content-Type": "application/json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("full_name")
        except Exception as e:
            print(f"[GitHub] Create repo failed: {e}")
            return None
    
    def upload_file(self, repo: str, path: str, content: Dict, message: str = None) -> bool:
        """Upload JSON file to repo."""
        if not self.connected:
            return False
        
        # Check if file exists
        sha = None
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/repos/{self.username}/{repo}/contents/{path}",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
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
                    "Content-Type": "application/json"
                }
            )
            urllib.request.urlopen(req, timeout=30)
            return True
        except Exception as e:
            print(f"[GitHub] Upload failed: {e}")
            return False
    
    def download_file(self, repo: str, path: str) -> Optional[Dict]:
        """Download JSON file from repo."""
        if not self.connected:
            return None
        
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/repos/{self.username}/{repo}/contents/{path}",
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            import base64
            content = base64.b64decode(data["content"])
            return json.loads(content)
        except Exception:
            return None
    
    def create_gist(self, filename: str, content: Dict, public: bool = False) -> Optional[str]:
        """Create a GitHub Gist."""
        try:
            req = urllib.request.Request(
                f"{self.API_BASE}/gists",
                data=json.dumps({
                    "description": f"GlacierEQ Mesh: {filename}",
                    "public": public,
                    "files": {
                        filename: {
                            "content": json.dumps(content, indent=2)
                        }
                    }
                }).encode(),
                headers={
                    "Authorization": f"token {self.token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0",
                    "Content-Type": "application/json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            return data.get("html_url")
        except Exception:
            return None


class CloudStorageManager:
    """Unified manager for all cloud storage providers."""
    
    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path or "~/.glaciereq/mesh/cloud.json").expanduser()
        self.configs: Dict[StorageProvider, StorageConfig] = {}
        self.bridges: Dict[StorageProvider, Any] = {}
        
        self._load_config()
    
    def _load_config(self):
        """Load cloud storage configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                    for provider_name, config in data.items():
                        provider = StorageProvider(provider_name)
                        config["provider"] = provider
                        self.configs[provider] = StorageConfig(**config)
            except Exception:
                pass
    
    def save_config(self):
        """Save cloud storage configuration."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {}
        for provider, config in self.configs.items():
            data[provider.value] = config.to_dict()
        
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def add_provider(self, provider: StorageProvider, credentials: Dict[str, str]) -> bool:
        """Add a cloud storage provider."""
        config = StorageConfig(
            provider=provider,
            credentials=credentials
        )
        self.configs[provider] = config
        
        # Create bridge
        if provider == StorageProvider.DROPBOX:
            self.bridges[provider] = DropboxBridge(credentials.get("access_token", ""))
        elif provider == StorageProvider.GOOGLE_DRIVE:
            self.bridges[provider] = GoogleDriveBridge(credentials)
        elif provider == StorageProvider.GITHUB:
            self.bridges[provider] = GitHubBridge(credentials.get("token", ""))
        
        self.save_config()
        return True
    
    def connect_all(self) -> Dict[StorageProvider, bool]:
        """Connect to all configured providers."""
        results = {}
        
        for provider, config in self.configs.items():
            if not config.enabled:
                continue
            
            bridge = self.bridges.get(provider)
            if bridge:
                results[provider] = bridge.connect()
            else:
                results[provider] = False
        
        return results
    
    def upload_knowledge(self, key: str, data: Dict, providers: List[StorageProvider] = None) -> Dict[StorageProvider, bool]:
        """Upload knowledge to cloud storage providers."""
        results = {}
        
        target_providers = providers or list(self.bridges.keys())
        
        for provider in target_providers:
            bridge = self.bridges.get(provider)
            if not bridge or not getattr(bridge, "connected", False):
                results[provider] = False
                continue
            
            try:
                if provider == StorageProvider.DROPBOX:
                    results[provider] = bridge.upload(f"/GlacierEQ/Mesh/{key}.json", data)
                elif provider == StorageProvider.GITHUB:
                    repo = bridge.get_or_create_repo("mesh-knowledge", "GlacierEQ Mesh Knowledge Store")
                    if repo:
                        results[provider] = bridge.upload_file(repo, f"{key}.json", data)
                    else:
                        results[provider] = False
                elif provider == StorageProvider.GOOGLE_DRIVE:
                    results[provider] = bridge.upload(f"{key}.json", data)
                else:
                    results[provider] = False
            except Exception as e:
                print(f"[{provider.value}] Upload failed: {e}")
                results[provider] = False
        
        return results
    
    def download_knowledge(self, key: str, providers: List[StorageProvider] = None) -> Optional[Dict]:
        """Download knowledge from cloud storage."""
        target_providers = providers or list(self.bridges.keys())
        
        for provider in target_providers:
            bridge = self.bridges.get(provider)
            if not bridge or not getattr(bridge, "connected", False):
                continue
            
            try:
                data = None
                
                if provider == StorageProvider.DROPBOX:
                    data = bridge.download(f"/GlacierEQ/Mesh/{key}.json")
                elif provider == StorageProvider.GITHUB:
                    repo = f"{bridge.username}/mesh-knowledge"
                    data = bridge.download_file(repo, f"{key}.json")
                elif provider == StorageProvider.GOOGLE_DRIVE:
                    # Would need to find file by name
                    pass
                
                if data:
                    return data
            except Exception:
                continue
        
        return None
    
    def sync_knowledge(self, knowledge_store: Dict[str, Any]) -> Dict[StorageProvider, bool]:
        """Sync knowledge store to all providers."""
        results = {}
        
        for provider, bridge in self.bridges.items():
            if not getattr(bridge, "connected", False):
                results[provider] = False
                continue
            
            try:
                success = True
                
                for key, data in knowledge_store.items():
                    if provider == StorageProvider.DROPBOX:
                        if not bridge.upload(f"/GlacierEQ/Mesh/{key}.json", data):
                            success = False
                    elif provider == StorageProvider.GITHUB:
                        repo = bridge.get_or_create_repo("mesh-knowledge")
                        if repo:
                            if not bridge.upload_file(repo, f"{key}.json", data):
                                success = False
                        else:
                            success = False
                
                results[provider] = success
            except Exception as e:
                print(f"[{provider.value}] Sync failed: {e}")
                results[provider] = False
        
        return results
    
    def get_status(self) -> Dict:
        """Get status of all cloud connections."""
        status = {}
        
        for provider, config in self.configs.items():
            bridge = self.bridges.get(provider)
            status[provider.value] = {
                "enabled": config.enabled,
                "connected": getattr(bridge, "connected", False),
                "last_sync": config.last_sync
            }
        
        return status


def create_cloud_manager(config_path: str = None) -> CloudStorageManager:
    """Create and return a cloud storage manager."""
    return CloudStorageManager(config_path)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="GlacierEQ Cloud Storage Bridge")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--add-dropbox", help="Add Dropbox access token")
    parser.add_argument("--add-github", help="Add GitHub token")
    parser.add_argument("--connect", action="store_true", help="Connect to all providers")
    args = parser.parse_args()
    
    manager = create_cloud_manager()
    
    if args.add_dropbox:
        manager.add_provider(StorageProvider.DROPBOX, {"access_token": args.add_dropbox})
        print("Dropbox added")
    
    if args.add_github:
        manager.add_provider(StorageProvider.GITHUB, {"token": args.add_github})
        print("GitHub added")
    
    if args.connect:
        results = manager.connect_all()
        for provider, success in results.items():
            print(f"{provider.value}: {'✅' if success else '❌'}")
    
    if args.status or not any([args.add_dropbox, args.add_github, args.connect]):
        print(json.dumps(manager.get_status(), indent=2))
