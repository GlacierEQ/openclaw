from __future__ import annotations

import json

from src.cloud_storage import CloudStorageManager


class FakeDropbox:
    connected = True
    def __init__(self):
        self.calls = []
    def upload(self, path, data):
        self.calls.append((path, data))
        return True


class FakeGitHub:
    connected = True
    def __init__(self):
        self.calls = []
    def upload_file(self, repo, path, data):
        self.calls.append((repo, path, data))
        return True


def test_provider_config_stores_environment_reference(tmp_path):
    config = tmp_path / "cloud.json"
    manager = CloudStorageManager(str(config))
    assert manager.configure_provider("github", credential_env="OPENCLAW_TEST_GH", target={"repo": "owner/repo"})
    state = json.loads(config.read_text())
    assert state["github"]["credential_env"] == "OPENCLAW_TEST_GH"
    assert "credentials" not in state["github"]


def test_sync_requires_explicit_github_target(tmp_path):
    manager = CloudStorageManager(str(tmp_path / "cloud.json"))
    manager.configs = {"github": {"enabled": True, "credential_env": "X", "target": {}, "last_sync": 0}}
    manager.bridges = {"github": FakeGitHub()}
    assert manager.sync_knowledge({"k": "v"}) == {"github": False}


def test_sync_uses_configured_targets(tmp_path):
    manager = CloudStorageManager(str(tmp_path / "cloud.json"))
    dropbox = FakeDropbox()
    github = FakeGitHub()
    manager.configs = {
        "dropbox": {"enabled": True, "credential_env": "D", "target": {"path": "/mesh/state.json"}, "last_sync": 0},
        "github": {"enabled": True, "credential_env": "G", "target": {"repo": "owner/repo", "path": "mesh/state.json"}, "last_sync": 0}
    }
    manager.bridges = {"dropbox": dropbox, "github": github}
    assert manager.sync_knowledge({"node": 1}) == {"dropbox": True, "github": True}
    assert dropbox.calls[0][0] == "/mesh/state.json"
    assert github.calls[0][:2] == ("owner/repo", "mesh/state.json")
