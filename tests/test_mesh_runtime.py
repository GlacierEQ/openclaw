from __future__ import annotations

import socket
import threading
import time

from src.mesh_runtime import MeshIntelligence, MeshNode, MeshTransport, NodeCapability, PersistentKnowledgeStore


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_local_mesh_is_truthfully_local_without_key(tmp_path):
    mesh = MeshIntelligence("node-a", shared_key="", state_path=str(tmp_path / "mesh.json"))
    assert mesh.network_enabled is False
    assert mesh.get_status()["claim"] == "LOCAL_ONLY_NO_MESH_KEY"


def test_knowledge_persists_across_instances(tmp_path):
    path = tmp_path / "mesh.json"
    first = PersistentKnowledgeStore("node-a", str(path))
    first.set("case/state", {"value": 7}, tags=["verified"])
    second = PersistentKnowledgeStore("node-a", str(path))
    assert second.get("case/state") == {"value": 7}


def test_merge_rejects_older_version(tmp_path):
    from src.mesh_runtime import KnowledgeEntry

    store = PersistentKnowledgeStore("node-a", str(tmp_path / "mesh.json"))
    current = store.set("k", "new")
    older = KnowledgeEntry("k", "old", "node-b", current.version - 1, current.timestamp + 100)
    assert store.merge(older) is False
    assert store.get("k") == "new"


def test_authenticated_tcp_transport_delivers_message():
    port_a = free_port()
    port_b = free_port()
    key = b"shared-test-key"
    received = []
    node_a = MeshNode("node-a", "a", "127.0.0.1", port_a, NodeCapability())
    node_b = MeshNode("node-b", "b", "127.0.0.1", port_b, NodeCapability())
    transport_b = MeshTransport(node_b, key, received.append)
    transport_b.running = True
    thread = threading.Thread(target=transport_b._serve, daemon=True)
    thread.start()
    time.sleep(0.05)
    transport_a = MeshTransport(node_a, key, lambda _: None)
    assert transport_a.send(node_b, "knowledge_update", {"entry": {"key": "x"}}) is True
    deadline = time.time() + 1.0
    while not received and time.time() < deadline:
        time.sleep(0.01)
    transport_b.stop()
    assert received
    assert received[0]["kind"] == "knowledge_update"
    assert received[0]["sender"] == "node-a"


def test_route_inference_never_fabricates_output(tmp_path):
    mesh = MeshIntelligence("node-a", shared_key="", state_path=str(tmp_path / "mesh.json"))
    result = mesh.route_inference("hello")
    assert result == {"status": "NO_VERIFIED_INFERENCE_ROUTE", "routable": False, "model": None}
    assert "response" not in result
