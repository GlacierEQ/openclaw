"""Authenticated local-network mesh runtime for OpenClaw.

Networking is disabled unless all nodes share OPENCLAW_MESH_KEY (or an explicit
key is passed). Without that key the mesh remains a fully functional local
knowledge store and reports network_enabled=false rather than inventing peers.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import struct
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MAX_MESSAGE_BYTES = 1024 * 1024
DISCOVERY_GROUP = "239.255.42.99"
DISCOVERY_PORT = 53539
DEFAULT_MESH_PORT = 8090


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sign(key: bytes, payload: Dict[str, Any]) -> str:
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def _verify(key: bytes, payload: Dict[str, Any], signature: str) -> bool:
    return hmac.compare_digest(_sign(key, payload), str(signature or ""))


def _memory_gb() -> float:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((pages * page_size) / (1024**3), 2)
    except (ValueError, OSError, AttributeError):
        return 0.0


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


@dataclass
class NodeCapability:
    memory_gb: float = 0.0
    models: List[str] = field(default_factory=list)
    specialties: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MeshNode:
    node_id: str
    hostname: str
    ip_address: str
    port: int
    capability: NodeCapability = field(default_factory=NodeCapability)
    last_seen: float = 0.0
    status: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["capability"] = self.capability.to_dict()
        return data

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "MeshNode":
        node_id = str(value.get("node_id", ""))
        ip = str(value.get("ip_address", ""))
        port = int(value.get("port", 0))
        if not node_id or len(node_id) > 128:
            raise ValueError("invalid node_id")
        try:
            socket.inet_aton(ip)
        except OSError as exc:
            raise ValueError("invalid IPv4 address") from exc
        if not 1 <= port <= 65535:
            raise ValueError("invalid port")
        cap = value.get("capability") or {}
        capability = NodeCapability(
            memory_gb=float(cap.get("memory_gb", 0.0)),
            models=[str(x) for x in cap.get("models", [])][:100],
            specialties=[str(x) for x in cap.get("specialties", [])][:100],
        )
        return cls(
            node_id=node_id,
            hostname=str(value.get("hostname", ""))[:255],
            ip_address=ip,
            port=port,
            capability=capability,
            last_seen=float(value.get("last_seen", 0.0)),
            status=str(value.get("status", "unknown"))[:32],
        )


@dataclass
class KnowledgeEntry:
    key: str
    value: Any
    author: str
    version: int
    timestamp: float
    ttl: float = 0.0
    tags: List[str] = field(default_factory=list)

    def expired(self, now: Optional[float] = None) -> bool:
        return self.ttl > 0 and (time.time() if now is None else now) - self.timestamp > self.ttl

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PersistentKnowledgeStore:
    def __init__(self, node_id: str, path: str = ".openclaw/mesh_state.json"):
        self.node_id = node_id
        self.path = Path(path)
        self.entries: Dict[str, KnowledgeEntry] = {}
        self._lock = threading.RLock()
        self._load()

    @staticmethod
    def _valid_key(key: str) -> bool:
        return bool(key) and len(key) <= 256 and all(ch.isalnum() or ch in "-_./:" for ch in key)

    def set(self, key: str, value: Any, *, tags: Optional[List[str]] = None, ttl: float = 0.0) -> KnowledgeEntry:
        if not self._valid_key(key):
            raise ValueError("invalid knowledge key")
        if len(_canonical(value)) > MAX_MESSAGE_BYTES // 2:
            raise ValueError("knowledge value too large")
        with self._lock:
            previous = self.entries.get(key)
            entry = KnowledgeEntry(
                key=key,
                value=value,
                author=self.node_id,
                version=(previous.version + 1) if previous else 1,
                timestamp=time.time(),
                ttl=max(0.0, float(ttl)),
                tags=list(tags or [])[:100],
            )
            self.entries[key] = entry
            self._save()
            return entry

    def merge(self, entry: KnowledgeEntry) -> bool:
        if not self._valid_key(entry.key) or entry.expired():
            return False
        with self._lock:
            current = self.entries.get(entry.key)
            incoming_rank = (entry.version, entry.timestamp, entry.author)
            current_rank = (current.version, current.timestamp, current.author) if current else (-1, -1.0, "")
            if incoming_rank <= current_rank:
                return False
            self.entries[entry.key] = entry
            self._save()
            return True

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            if entry.expired():
                self.entries.pop(key, None)
                self._save()
                return None
            return entry.value

    def export(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {key: entry.to_dict() for key, entry in self.entries.items() if not entry.expired()}

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for key, raw in (data.get("entries", {}) if isinstance(data, dict) else {}).items():
                entry = KnowledgeEntry(**raw)
                if not entry.expired() and self._valid_key(key):
                    self.entries[key] = entry
        except (OSError, ValueError, TypeError):
            self.entries = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": "openclaw.mesh-state.v1", "node_id": self.node_id, "entries": self.export()}
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


class MeshTransport:
    """Tiny authenticated TCP transport plus multicast peer discovery."""

    def __init__(self, node: MeshNode, key: bytes, on_message: Callable[[Dict[str, Any]], None]):
        self.node = node
        self.key = key
        self.on_message = on_message
        self.peers: Dict[str, MeshNode] = {}
        self.running = False
        self._threads: List[threading.Thread] = []
        self._server: Optional[socket.socket] = None
        self._lock = threading.RLock()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._threads = [
            threading.Thread(target=self._serve, daemon=True, name="openclaw-mesh-server"),
            threading.Thread(target=self._discover, daemon=True, name="openclaw-mesh-discovery"),
            threading.Thread(target=self._beacon, daemon=True, name="openclaw-mesh-beacon"),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self.running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        for thread in self._threads:
            thread.join(timeout=1.5)

    def _envelope(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = {"kind": kind, "sender": self.node.node_id, "timestamp": time.time(), "payload": payload}
        return {"body": body, "signature": _sign(self.key, body)}

    def _decode(self, raw: bytes) -> Optional[Dict[str, Any]]:
        if not raw or len(raw) > MAX_MESSAGE_BYTES:
            return None
        try:
            envelope = json.loads(raw.decode("utf-8"))
            body = envelope["body"]
            if not isinstance(body, dict) or not _verify(self.key, body, envelope.get("signature", "")):
                return None
            if abs(time.time() - float(body.get("timestamp", 0.0))) > 120:
                return None
            return body
        except (ValueError, TypeError, KeyError):
            return None

    def _serve(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server = server
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self.node.port))
        server.listen(16)
        server.settimeout(1.0)
        while self.running:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(2.0)
                try:
                    header = conn.recv(4)
                    if len(header) != 4:
                        continue
                    size = struct.unpack("!I", header)[0]
                    if size <= 0 or size > MAX_MESSAGE_BYTES:
                        continue
                    chunks = bytearray()
                    while len(chunks) < size:
                        part = conn.recv(min(65536, size - len(chunks)))
                        if not part:
                            break
                        chunks.extend(part)
                    if len(chunks) != size:
                        continue
                    body = self._decode(bytes(chunks))
                    if body:
                        self.on_message(body)
                except (OSError, ValueError):
                    continue

    def _beacon(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        while self.running:
            envelope = self._envelope("beacon", {"node": self.node.to_dict()})
            try:
                sock.sendto(_canonical(envelope), (DISCOVERY_GROUP, DISCOVERY_PORT))
            except OSError:
                pass
            time.sleep(5.0)
        sock.close()

    def _discover(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", DISCOVERY_PORT))
            membership = struct.pack("4sL", socket.inet_aton(DISCOVERY_GROUP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            sock.settimeout(1.0)
            while self.running:
                try:
                    raw, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break
                body = self._decode(raw)
                if not body or body.get("kind") != "beacon" or body.get("sender") == self.node.node_id:
                    continue
                try:
                    peer = MeshNode.from_dict(body.get("payload", {}).get("node", {}))
                except ValueError:
                    continue
                peer.last_seen = time.time()
                peer.status = "authenticated"
                with self._lock:
                    self.peers[peer.node_id] = peer
        finally:
            sock.close()

    def alive_peers(self, timeout: float = 20.0) -> List[MeshNode]:
        cutoff = time.time() - timeout
        with self._lock:
            return [peer for peer in self.peers.values() if peer.last_seen >= cutoff]

    def send(self, peer: MeshNode, kind: str, payload: Dict[str, Any]) -> bool:
        raw = _canonical(self._envelope(kind, payload))
        if len(raw) > MAX_MESSAGE_BYTES:
            return False
        try:
            with socket.create_connection((peer.ip_address, peer.port), timeout=2.0) as conn:
                conn.sendall(struct.pack("!I", len(raw)) + raw)
            return True
        except OSError:
            return False

    def broadcast(self, kind: str, payload: Dict[str, Any]) -> Dict[str, bool]:
        return {peer.node_id: self.send(peer, kind, payload) for peer in self.alive_peers()}


class MeshIntelligence:
    def __init__(self, node_id: Optional[str] = None, shared_key: Optional[str] = None, *, port: int = DEFAULT_MESH_PORT, state_path: str = ".openclaw/mesh_state.json"):
        self.node_id = node_id or f"node-{uuid.uuid4().hex[:12]}"
        if not 1 <= int(port) <= 65535:
            raise ValueError("invalid mesh port")
        capability = NodeCapability(memory_gb=_memory_gb(), specialties=["knowledge_store"])
        self.node = MeshNode(self.node_id, socket.gethostname(), _local_ip(), int(port), capability)
        self.store = PersistentKnowledgeStore(self.node_id, state_path)
        self.knowledge = self.store.entries
        key_value = shared_key if shared_key is not None else os.getenv("OPENCLAW_MESH_KEY", "")
        self._network_key = key_value.encode("utf-8") if key_value else None
        self.transport = MeshTransport(self.node, self._network_key, self._handle_message) if self._network_key else None
        self.running = False
        self._on_peer_callbacks: List[Callable[[MeshNode], None]] = []
        self._on_knowledge_callbacks: List[Callable[[KnowledgeEntry], None]] = []

    @property
    def network_enabled(self) -> bool:
        return self.transport is not None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.node.status = "local" if not self.transport else "active"
        if self.transport:
            self.transport.start()

    def stop(self) -> None:
        if self.transport:
            self.transport.stop()
        self.running = False
        self.node.status = "stopped"

    def store_knowledge(self, key: str, value: Any, tags: Optional[List[str]] = None, ttl: float = 0.0) -> KnowledgeEntry:
        entry = self.store.set(key, value, tags=tags, ttl=ttl)
        if self.transport:
            self.transport.broadcast("knowledge_update", {"entry": entry.to_dict()})
        for callback in self._on_knowledge_callbacks:
            callback(entry)
        return entry

    def get_knowledge(self, key: str) -> Optional[Any]:
        return self.store.get(key)

    def query_peers(self, capability_needed: Optional[str] = None) -> List[MeshNode]:
        peers = self.transport.alive_peers() if self.transport else []
        if capability_needed:
            peers = [peer for peer in peers if capability_needed in peer.capability.specialties]
        return peers

    def route_inference(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Return a route decision only; this method never fabricates inference output."""
        if not prompt or len(prompt.encode("utf-8")) > MAX_MESSAGE_BYTES // 2:
            return {"status": "INVALID_PROMPT", "routable": False}
        candidates = [peer for peer in self.query_peers() if (not model or model in peer.capability.models)]
        if candidates:
            chosen = sorted(candidates, key=lambda peer: (len(peer.capability.models), peer.capability.memory_gb), reverse=True)[0]
            return {"status": "ROUTE_AVAILABLE", "routable": True, "node": chosen.to_dict(), "model": model}
        return {"status": "NO_VERIFIED_INFERENCE_ROUTE", "routable": False, "model": model}

    def on_peer(self, callback: Callable[[MeshNode], None]) -> None:
        self._on_peer_callbacks.append(callback)

    def on_knowledge(self, callback: Callable[[KnowledgeEntry], None]) -> None:
        self._on_knowledge_callbacks.append(callback)

    def _handle_message(self, body: Dict[str, Any]) -> None:
        kind = body.get("kind")
        if kind == "knowledge_update":
            raw = body.get("payload", {}).get("entry", {})
            try:
                entry = KnowledgeEntry(**raw)
            except (TypeError, ValueError):
                return
            if entry.author == self.node_id:
                return
            if self.store.merge(entry):
                for callback in self._on_knowledge_callbacks:
                    callback(entry)

    def get_status(self) -> Dict[str, Any]:
        peers = self.transport.alive_peers() if self.transport else []
        return {
            "node_id": self.node_id,
            "hostname": self.node.hostname,
            "ip": self.node.ip_address,
            "port": self.node.port,
            "running": self.running,
            "network_enabled": self.network_enabled,
            "authenticated_peers": len(peers),
            "knowledge_entries": len(self.store.export()),
            "capability": self.node.capability.to_dict(),
            "claim": "AUTHENTICATED_LAN_MESH" if self.network_enabled else "LOCAL_ONLY_NO_MESH_KEY",
        }


def create_mesh(node_id: Optional[str] = None, shared_key: Optional[str] = None) -> MeshIntelligence:
    return MeshIntelligence(node_id=node_id, shared_key=shared_key)
