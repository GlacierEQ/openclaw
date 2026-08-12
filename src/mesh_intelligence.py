#!/usr/bin/env python3
"""
GlacierEQ Mesh Intelligence — Distributed AI Across All Devices

Philosophy: Intelligence, processing, and memory should be distributed.
            Power can come from surprising places: your laptop, a phone,
            a Dropbox folder, a Google Drive, a GitHub repo.

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │                MESH INTELLIGENCE                     │
    ├─────────────────────────────────────────────────────┤
    │  DISCOVERY  →  Devices find each other (UDP/mDNS)   │
    │  TRANSPORT  →  QUIC/iroh for fast activation        │
    │  GOSSIP     →  Real-time state broadcast             │
    │  CRDT       →  Conflict-free state sync              │
    │  KNOWLEDGE  →  Cloud storage as durable memory       │
    │  INFERENCE  →  Route to best available compute       │
    └─────────────────────────────────────────────────────┘
"""

import hashlib
import json
import os
import socket
import struct
import threading
import time
import urllib.request
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
import uuid


class NodeRole(Enum):
    """Node roles in the mesh."""
    COMPUTE = "compute"      # Can run inference
    STORAGE = "storage"      # Has knowledge/storage
    ROUTER = "router"        # Routes between nodes
    GATEWAY = "gateway"      # Connects to cloud
    MOBILE = "mobile"        # Phone/tablet (limited compute)
    EDGE = "edge"            # Edge device (Raspberry Pi, etc.)


class NodeStatus(Enum):
    """Node status in the mesh."""
    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ACTIVE = "active"
    IDLE = "idle"
    FAILED = "failed"


class KnowledgeSource(Enum):
    """Sources of knowledge in the mesh."""
    LOCAL = "local"
    DROPBOX = "dropbox"
    GOOGLE_DRIVE = "google_drive"
    GITHUB = "github"
    GDRIVE = "gdrive"
    ONEDRIVE = "onedrive"
    ICLOUD = "icloud"
    MESH = "mesh"  # From another node


@dataclass
class NodeCapability:
    """Capabilities of a mesh node."""
    compute_power: float = 0.0  # FLOPS (normalized)
    memory_gb: float = 0.0
    vram_gb: float = 0.0
    storage_gb: float = 0.0
    bandwidth_mbps: float = 0.0
    inference_speed: float = 0.0  # tokens/sec
    models: List[str] = field(default_factory=list)
    specialties: List[str] = field(default_factory=list)


@dataclass
class MeshNode:
    """A node in the mesh intelligence network."""
    node_id: str
    hostname: str
    ip_address: str
    port: int
    role: NodeRole
    status: NodeStatus = NodeStatus.UNKNOWN
    capability: NodeCapability = field(default_factory=NodeCapability)
    last_seen: float = 0.0
    latency_ms: float = 0.0
    knowledge_sources: List[KnowledgeSource] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["role"] = self.role.value
        d["status"] = self.status.value
        d["knowledge_sources"] = [s.value for s in self.knowledge_sources]
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MeshNode":
        data["role"] = NodeRole(data["role"])
        data["status"] = NodeStatus(data["status"])
        data["knowledge_sources"] = [KnowledgeSource(s) for s in data.get("knowledge_sources", [])]
        if "capability" in data and isinstance(data["capability"], dict):
            data["capability"] = NodeCapability(**data["capability"])
        return cls(**data)


@dataclass
class KnowledgeEntry:
    """A piece of knowledge in the mesh."""
    entry_id: str
    source: KnowledgeSource
    key: str
    value: Any
    timestamp: float
    author: str  # node_id
    version: int = 1
    ttl: float = 0.0  # 0 = permanent
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["source"] = self.source.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "KnowledgeEntry":
        data["source"] = KnowledgeSource(data["source"])
        return cls(**data)


@dataclass
class GossipMessage:
    """A gossip message for state propagation."""
    msg_id: str
    sender: str
    msg_type: str  # "heartbeat", "knowledge", "inference_request", "inference_result"
    payload: Dict[str, Any]
    timestamp: float
    ttl: int = 3  # Max hops
    
    def to_dict(self) -> Dict:
        return asdict(self)


class MeshDiscovery:
    """UDP multicast discovery for mesh nodes."""
    
    MULTICAST_GROUP = "224.0.0.251"
    DISCOVERY_PORT = 5353
    BEACON_INTERVAL = 5.0
    
    def __init__(self, node: MeshNode):
        self.node = node
        self.peers: Dict[str, MeshNode] = {}
        self.running = False
        self._callbacks = []
    
    def start(self):
        """Start discovery service."""
        self.running = True
        threading.Thread(target=self._beacon_loop, daemon=True).start()
        threading.Thread(target=self._listener_loop, daemon=True).start()
    
    def stop(self):
        """Stop discovery service."""
        self.running = False
    
    def on_peer_discovered(self, callback):
        """Register callback for peer discovery."""
        self._callbacks.append(callback)
    
    def _beacon_loop(self):
        """Broadcast beacon messages."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        while self.running:
            beacon = json.dumps({
                "type": "beacon",
                "node": self.node.to_dict()
            }).encode()
            
            try:
                sock.sendto(beacon, (self.MULTICAST_GROUP, self.DISCOVERY_PORT))
            except Exception:
                pass
            
            time.sleep(self.BEACON_INTERVAL)
        
        sock.close()
    
    def _listener_loop(self):
        """Listen for beacon messages."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.DISCOVERY_PORT))
        
        mreq = struct.pack(
            "4sl",
            socket.inet_aton(self.MULTICAST_GROUP),
            socket.INADDR_ANY
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)
        
        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                msg = json.loads(data.decode())
                
                if msg.get("type") == "beacon":
                    peer = MeshNode.from_dict(msg["node"])
                    if peer.node_id != self.node.node_id:
                        self._handle_peer(peer)
            except socket.timeout:
                continue
            except Exception:
                continue
        
        sock.close()
    
    def _handle_peer(self, peer: MeshNode):
        """Handle discovered peer."""
        is_new = peer.node_id not in self.peers
        
        peer.last_seen = time.time()
        peer.status = NodeStatus.DISCOVERED
        self.peers[peer.node_id] = peer
        
        if is_new:
            for cb in self._callbacks:
                try:
                    cb(peer)
                except Exception:
                    pass


class GossipProtocol:
    """Gossip protocol for mesh state propagation."""
    
    def __init__(self, node: MeshNode):
        self.node = node
        self.messages: Dict[str, GossipMessage] = {}
        self.peers: Dict[str, MeshNode] = {}
        self._callbacks = []
        self.running = False
    
    def start(self):
        """Start gossip service."""
        self.running = True
        threading.Thread(target=self._gossip_loop, daemon=True).start()
    
    def stop(self):
        """Stop gossip service."""
        self.running = False
    
    def on_message(self, callback):
        """Register callback for gossip messages."""
        self._callbacks.append(callback)
    
    def broadcast(self, msg_type: str, payload: Dict[str, Any]):
        """Broadcast a gossip message."""
        msg = GossipMessage(
            msg_id=str(uuid.uuid4()),
            sender=self.node.node_id,
            msg_type=msg_type,
            payload=payload,
            timestamp=time.time()
        )
        self.messages[msg.msg_id] = msg
        self._propagate(msg)
    
    def _gossip_loop(self):
        """Periodic gossip exchange."""
        while self.running:
            self._exchange_gossip()
            time.sleep(10)
    
    def _exchange_gossip(self):
        """Exchange gossip with random peers."""
        # In real implementation, this would send messages to random peers
        pass
    
    def _propagate(self, msg: GossipMessage):
        """Propagate message to peers."""
        # In real implementation, this would send to connected peers
        pass
    
    def _handle_message(self, msg: GossipMessage):
        """Handle incoming gossip message."""
        if msg.msg_id in self.messages:
            return  # Already seen
        
        self.messages[msg.msg_id] = msg
        msg.ttl -= 1
        
        if msg.ttl > 0:
            self._propagate(msg)
        
        for cb in self._callbacks:
            try:
                cb(msg)
            except Exception:
                pass


class CRDTStore:
    """Conflict-free Replicated Data Types for distributed state."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.state: Dict[str, Dict] = {}  # key -> {value, timestamp, node_id}
        self.vector_clock: Dict[str, int] = {}  # node_id -> counter
    
    def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        entry = self.state.get(key)
        if entry:
            return entry["value"]
        return None
    
    def set(self, key: str, value: Any):
        """Set value using LWW-Register semantics."""
        self.vector_clock[self.node_id] = self.vector_clock.get(self.node_id, 0) + 1
        
        self.state[key] = {
            "value": value,
            "timestamp": time.time(),
            "node_id": self.node_id,
            "clock": self.vector_clock.copy()
        }
    
    def merge(self, other_state: Dict[str, Dict]):
        """Merge remote state using conflict resolution."""
        for key, remote_entry in other_state.items():
            local_entry = self.state.get(key)
            
            if not local_entry:
                self.state[key] = remote_entry
            else:
                # LWW-Register: latest timestamp wins
                if remote_entry["timestamp"] > local_entry["timestamp"]:
                    self.state[key] = remote_entry
                elif remote_entry["timestamp"] == local_entry["timestamp"]:
                    # Tie-break by node_id
                    if remote_entry["node_id"] > local_entry["node_id"]:
                        self.state[key] = remote_entry
    
    def export_state(self) -> Dict[str, Dict]:
        """Export full state for sync."""
        return self.state.copy()
    
    def import_state(self, state: Dict[str, Dict]):
        """Import and merge state."""
        self.merge(state)


class CloudStorageBridge:
    """Bridge to cloud storage services for knowledge distribution."""
    
    def __init__(self):
        self.connections: Dict[KnowledgeSource, Dict] = {}
        self.sync_interval = 300  # 5 minutes
    
    def connect_dropbox(self, access_token: str) -> bool:
        """Connect to Dropbox."""
        try:
            # Test connection
            req = urllib.request.Request(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            self.connections[KnowledgeSource.DROPBOX] = {
                "access_token": access_token,
                "account_id": data.get("account_id"),
                "name": data.get("name", {}).get("display_name"),
                "connected_at": time.time()
            }
            return True
        except Exception as e:
            print(f"Dropbox connection failed: {e}")
            return False
    
    def connect_google_drive(self, credentials: Dict) -> bool:
        """Connect to Google Drive."""
        try:
            # Simplified - in production use OAuth2
            self.connections[KnowledgeSource.GOOGLE_DRIVE] = {
                "credentials": credentials,
                "connected_at": time.time()
            }
            return True
        except Exception as e:
            print(f"Google Drive connection failed: {e}")
            return False
    
    def connect_github(self, token: str) -> bool:
        """Connect to GitHub."""
        try:
            req = urllib.request.Request(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {token}",
                    "User-Agent": "GlacierEQ-Mesh/1.0"
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            self.connections[KnowledgeSource.GITHUB] = {
                "token": token,
                "username": data.get("login"),
                "connected_at": time.time()
            }
            return True
        except Exception as e:
            print(f"GitHub connection failed: {e}")
            return False
    
    def upload_knowledge(self, source: KnowledgeSource, key: str, data: Dict) -> bool:
        """Upload knowledge to cloud storage."""
        if source not in self.connections:
            return False
        
        try:
            if source == KnowledgeSource.DROPBOX:
                return self._upload_dropbox(key, data)
            elif source == KnowledgeSource.GITHUB:
                return self._upload_github(key, data)
            elif source == KnowledgeSource.GOOGLE_DRIVE:
                return self._upload_gdrive(key, data)
        except Exception as e:
            print(f"Upload failed: {e}")
            return False
        
        return False
    
    def download_knowledge(self, source: KnowledgeSource, key: str) -> Optional[Dict]:
        """Download knowledge from cloud storage."""
        if source not in self.connections:
            return None
        
        try:
            if source == KnowledgeSource.DROPBOX:
                return self._download_dropbox(key)
            elif source == KnowledgeSource.GITHUB:
                return self._download_github(key)
            elif source == KnowledgeSource.GOOGLE_DRIVE:
                return self._download_gdrive(key)
        except Exception as e:
            print(f"Download failed: {e}")
        
        return None
    
    def _upload_dropbox(self, key: str, data: Dict) -> bool:
        """Upload to Dropbox."""
        conn = self.connections[KnowledgeSource.DROPBOX]
        path = f"/GlacierEQ/Mesh/{key}.json"
        
        req = urllib.request.Request(
            "https://content.dropboxapi.com/2/files/upload",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {conn['access_token']}",
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
    
    def _download_dropbox(self, key: str) -> Optional[Dict]:
        """Download from Dropbox."""
        conn = self.connections[KnowledgeSource.DROPBOX]
        path = f"/GlacierEQ/Mesh/{key}.json"
        
        req = urllib.request.Request(
            "https://content.dropboxapi.com/2/files/download",
            headers={
                "Authorization": f"Bearer {conn['access_token']}",
                "Dropbox-API-Arg": json.dumps({"path": path})
            }
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    
    def _upload_github(self, key: str, data: Dict) -> bool:
        """Upload to GitHub as gist or repo file."""
        conn = self.connections[KnowledgeSource.GITHUB]
        
        # Create/update file in mesh-knowledge repo
        content = json.dumps(data, indent=2)
        sha = hashlib.sha1(content.encode()).hexdigest()
        
        req = urllib.request.Request(
            f"https://api.github.com/repos/{conn['username']}/mesh-knowledge/contents/{key}.json",
            data=json.dumps({
                "message": f"Update mesh knowledge: {key}",
                "content": __import__("base64").b64encode(content.encode()).decode(),
                "sha": sha[:40]  # Would need to get actual sha first
            }).encode(),
            headers={
                "Authorization": f"token {conn['token']}",
                "User-Agent": "GlacierEQ-Mesh/1.0",
                "Content-Type": "application/json"
            }
        )
        
        try:
            urllib.request.urlopen(req, timeout=30)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Repo doesn't exist, create it
                return self._create_github_repo(conn, key, content)
            return False
    
    def _create_github_repo(self, conn: Dict, key: str, content: str) -> bool:
        """Create mesh-knowledge repo on GitHub."""
        req = urllib.request.Request(
            "https://api.github.com/user/repos",
            data=json.dumps({
                "name": "mesh-knowledge",
                "description": "GlacierEQ Mesh Intelligence Knowledge Store",
                "auto_init": True,
                "private": True
            }).encode(),
            headers={
                "Authorization": f"token {conn['token']}",
                "User-Agent": "GlacierEQ-Mesh/1.0",
                "Content-Type": "application/json"
            }
        )
        
        try:
            urllib.request.urlopen(req, timeout=30)
            return True
        except Exception:
            return False
    
    def _download_github(self, key: str) -> Optional[Dict]:
        """Download from GitHub."""
        conn = self.connections[KnowledgeSource.GITHUB]
        
        req = urllib.request.Request(
            f"https://api.github.com/repos/{conn['username']}/mesh-knowledge/contents/{key}.json",
            headers={
                "Authorization": f"token {conn['token']}",
                "User-Agent": "GlacierEQ-Mesh/1.0"
            }
        )
        
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            import base64
            return json.loads(base64.b64decode(data["content"]))
        except Exception:
            return None
    
    def _upload_gdrive(self, key: str, data: Dict) -> bool:
        """Upload to Google Drive."""
        # Simplified - would use Google Drive API v3
        return False
    
    def _download_gdrive(self, key: str) -> Optional[Dict]:
        """Download from Google Drive."""
        # Simplified - would use Google Drive API v3
        return None


class MeshIntelligence:
    """Main mesh intelligence orchestrator."""
    
    def __init__(self, node_id: str = None):
        self.node_id = node_id or str(uuid.uuid4())[:8]
        
        # Detect local capabilities
        hostname = socket.gethostname()
        ip = self._get_local_ip()
        
        self.node = MeshNode(
            node_id=self.node_id,
            hostname=hostname,
            ip_address=ip,
            port=8090,
            role=NodeRole.COMPUTE,
            capability=self._detect_capability(),
            knowledge_sources=[KnowledgeSource.LOCAL]
        )
        
        # Components
        self.discovery = MeshDiscovery(self.node)
        self.gossip = GossipProtocol(self.node)
        self.crdt = CRDTStore(self.node_id)
        self.cloud = CloudStorageBridge()
        
        # State
        self.peers: Dict[str, MeshNode] = {}
        self.knowledge: Dict[str, KnowledgeEntry] = {}
        self.running = False
        
        # Callbacks
        self._on_peer_callbacks = []
        self._on_knowledge_callbacks = []
    
    def start(self):
        """Start mesh intelligence."""
        self.running = True
        
        # Start discovery
        self.discovery.on_peer_discovered(self._handle_peer)
        self.discovery.start()
        
        # Start gossip
        self.gossip.on_message(self._handle_gossip)
        self.gossip.start()
        
        # Announce self
        self.gossip.broadcast("node_join", {
            "node": self.node.to_dict()
        })
        
        print(f"[Mesh] Node {self.node_id} started on {self.node.ip_address}:{self.node.port}")
        print(f"[Mesh] Role: {self.node.role.value}")
        print(f"[Mesh] Discovery: UDP multicast on {self.discovery.MULTICAST_GROUP}:{self.discovery.DISCOVERY_PORT}")
    
    def stop(self):
        """Stop mesh intelligence."""
        self.running = False
        self.discovery.stop()
        self.gossip.stop()
        
        self.gossip.broadcast("node_leave", {
            "node_id": self.node_id
        })
        
        print(f"[Mesh] Node {self.node_id} stopped")
    
    def connect_cloud(self, source: KnowledgeSource, **kwargs) -> bool:
        """Connect to cloud storage."""
        if source == KnowledgeSource.DROPBOX:
            return self.cloud.connect_dropbox(kwargs.get("access_token", ""))
        elif source == KnowledgeSource.GOOGLE_DRIVE:
            return self.cloud.connect_google_drive(kwargs.get("credentials", {}))
        elif source == KnowledgeSource.GITHUB:
            return self.cloud.connect_github(kwargs.get("token", ""))
        return False
    
    def store_knowledge(self, key: str, value: Any, tags: List[str] = None):
        """Store knowledge locally and broadcast to mesh."""
        entry = KnowledgeEntry(
            entry_id=str(uuid.uuid4())[:8],
            source=KnowledgeSource.LOCAL,
            key=key,
            value=value,
            timestamp=time.time(),
            author=self.node_id,
            tags=tags or []
        )
        
        self.knowledge[key] = entry
        self.crdt.set(f"knowledge:{key}", entry.to_dict())
        
        # Broadcast to mesh
        self.gossip.broadcast("knowledge_update", {
            "entry": entry.to_dict()
        })
        
        # Sync to cloud if connected
        for source in self.node.knowledge_sources:
            if source != KnowledgeSource.LOCAL and source != KnowledgeSource.MESH:
                self.cloud.upload_knowledge(source, key, entry.to_dict())
    
    def get_knowledge(self, key: str) -> Optional[Any]:
        """Get knowledge from local store or mesh."""
        # Check local
        entry = self.knowledge.get(key)
        if entry:
            return entry.value
        
        # Check CRDT
        value = self.crdt.get(f"knowledge:{key}")
        if value:
            return value.get("value")
        
        # Would query peers in full implementation
        return None
    
    def query_peers(self, capability_needed: str = None) -> List[MeshNode]:
        """Find peers with specific capability."""
        results = []
        for peer in self.peers.values():
            if peer.status in [NodeStatus.CONNECTED, NodeStatus.ACTIVE]:
                if capability_needed is None:
                    results.append(peer)
                elif capability_needed in peer.capability.specialties:
                    results.append(peer)
        return sorted(results, key=lambda p: p.capability.compute_power, reverse=True)
    
    def route_inference(self, prompt: str, model: str = None) -> Dict:
        """Route inference to best available compute."""
        # Check local first
        if self.node.capability.inference_speed > 0:
            return {
                "node": self.node.to_dict(),
                "source": "local",
                "prompt": prompt
            }
        
        # Find best peer
        peers = self.query_peers("inference")
        if peers:
            best = peers[0]
            return {
                "node": best.to_dict(),
                "source": "mesh",
                "prompt": prompt,
                "latency_ms": best.latency_ms
            }
        
        # Fallback to cloud
        return {
            "source": "cloud",
            "prompt": prompt,
            "message": "No local/mesh compute available"
        }
    
    def on_peer(self, callback):
        """Register peer discovery callback."""
        self._on_peer_callbacks.append(callback)
    
    def on_knowledge(self, callback):
        """Register knowledge update callback."""
        self._on_knowledge_callbacks.append(callback)
    
    def _handle_peer(self, peer: MeshNode):
        """Handle discovered peer."""
        self.peers[peer.node_id] = peer
        print(f"[Mesh] Peer discovered: {peer.hostname} ({peer.ip_address}) [{peer.role.value}]")
        
        for cb in self._on_peer_callbacks:
            try:
                cb(peer)
            except Exception:
                pass
    
    def _handle_gossip(self, msg: GossipMessage):
        """Handle gossip message."""
        if msg.msg_type == "node_join":
            node_data = msg.payload.get("node")
            if node_data:
                peer = MeshNode.from_dict(node_data)
                if peer.node_id != self.node_id:
                    self._handle_peer(peer)
        
        elif msg.msg_type == "knowledge_update":
            entry_data = msg.payload.get("entry")
            if entry_data:
                entry = KnowledgeEntry.from_dict(entry_data)
                if entry.author != self.node_id:
                    self.knowledge[entry.key] = entry
                    
                    for cb in self._on_knowledge_callbacks:
                        try:
                            cb(entry)
                        except Exception:
                            pass
    
    def _detect_capability(self) -> NodeCapability:
        """Detect local compute capabilities."""
        import platform
        import subprocess
        
        capability = NodeCapability()
        
        # Detect memory
        try:
            if platform.system() == "Darwin":
                result = subprocess.run(["sysctl", "-n", "hw.memsize"], 
                                      capture_output=True, text=True, timeout=5)
                capability.memory_gb = int(result.stdout.strip()) / (1024**3)
            elif platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    for line in f:
                        if "MemTotal" in line:
                            capability.memory_gb = int(line.split()[1]) / (1024**2)
                            break
        except Exception:
            capability.memory_gb = 8.0  # Default assumption
        
        # Check for GPU/VRAM
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", 
                                   "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                capability.vram_gb = float(result.stdout.strip().split("\n")[0]) / 1024
        except Exception:
            pass
        
        # Check Ollama models
        try:
            result = subprocess.run(["ollama", "list"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                models = [line.split()[0] for line in result.stdout.strip().split("\n")[1:] if line.strip()]
                capability.models = models
                capability.inference_speed = 10.0 if models else 0.0  # Rough estimate
        except Exception:
            pass
        
        # Set specialties based on capabilities
        if capability.vram_gb > 8:
            capability.specialties.append("heavy_inference")
            capability.compute_power = 100.0
        elif capability.memory_gb > 16:
            capability.specialties.append("cpu_inference")
            capability.compute_power = 50.0
        else:
            capability.specialties.append("lightweight")
            capability.compute_power = 10.0
        
        if capability.models:
            capability.specialties.append("ollama")
        
        return capability
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def get_status(self) -> Dict:
        """Get mesh status."""
        return {
            "node_id": self.node_id,
            "hostname": self.node.hostname,
            "ip": self.node.ip_address,
            "port": self.node.port,
            "role": self.node.role.value,
            "capabilities": {
                "compute_power": self.node.capability.compute_power,
                "memory_gb": self.node.capability.memory_gb,
                "vram_gb": self.node.capability.vram_gb,
                "models": self.node.capability.models,
                "specialties": self.node.capability.specialties
            },
            "peers": len(self.peers),
            "knowledge_entries": len(self.knowledge),
            "cloud_connections": list(self.cloud.connections.keys()),
            "running": self.running
        }


def create_mesh(node_id: str = None) -> MeshIntelligence:
    """Create and return a mesh intelligence instance."""
    return MeshIntelligence(node_id)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="GlacierEQ Mesh Intelligence")
    parser.add_argument("--node-id", help="Node ID")
    parser.add_argument("--port", type=int, default=8090, help="Port")
    parser.add_argument("--status", action="store_true", help="Show status")
    args = parser.parse_args()
    
    mesh = create_mesh(args.node_id)
    mesh.node.port = args.port
    
    if args.status:
        print(json.dumps(mesh.get_status(), indent=2))
    else:
        mesh.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            mesh.stop()
