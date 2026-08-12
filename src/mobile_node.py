#!/usr/bin/env python3
"""
Mobile Compute Node — Phones/Tablets as AI Mesh Nodes

Philosophy: Every device is a potential compute node.
            Phones have NPUs, tablets have GPUs, watches have sensors.
            Intelligence should flow through all of them.

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │              MOBILE COMPUTE NODE                     │
    ├─────────────────────────────────────────────────────┤
    │  DISCOVERY  →  mDNS/Bonjour (same network)          │
    │  TRANSPORT  →  WebSocket/QUIC (low latency)         │
    │  INFERENCE  →  ExecuTorch/llama.cpp (on-device)     │
    │  STATE      →  CRDT (local-first)                   │
    │  SYNC       →  Cloud storage (Dropbox/Drive)        │
    └─────────────────────────────────────────────────────┘
"""

import json
import os
import platform
import socket
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any


class DeviceType(Enum):
    """Types of mobile devices."""
    PHONE = "phone"
    TABLET = "tablet"
    WATCH = "watch"
    HEADPHONE = "headphone"
    TV = "tv"
    CAR = "car"
    IOT = "iot"


class NPUChip(Enum):
    """Neural Processing Unit chips."""
    APPLE_NEURAL_ENGINE = "ane"
    QUALCOMM_HEXAGON = "hexagon"
    MEDIATEK_APU = "apu"
    SAMSUNG_NPU = "samsung_npu"
    GOOGLE_TENSOR = "tensor"
    MEDIATEK_DIMENSITY = "dimensity"
    UNKNOWN = "unknown"


@dataclass
class MobileCapability:
    """Capabilities of a mobile device."""
    device_type: DeviceType
    npu_chip: NPUChip = NPUChip.UNKNOWN
    npu_tops: float = 0.0  # Tera Operations Per Second
    gpu_tops: float = 0.0
    ram_gb: float = 0.0
    storage_gb: float = 0.0
    battery_percent: float = 100.0
    is_charging: bool = False
    thermal_state: str = "normal"  # normal, warm, hot, critical
    wifi_strength: float = 1.0  # 0.0 to 1.0
    max_context_length: int = 2048
    supported_models: List[str] = None
    
    def __post_init__(self):
        if self.supported_models is None:
            self.supported_models = []
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["device_type"] = self.device_type.value
        d["npu_chip"] = self.npu_chip.value
        return d
    
    @property
    def compute_budget(self) -> float:
        """Calculate compute budget based on current state."""
        budget = 1.0
        
        # Battery factor
        if self.battery_percent < 20:
            budget *= 0.2
        elif self.battery_percent < 50:
            budget *= 0.5
        
        # Charging bonus
        if self.is_charging:
            budget *= 1.5
        
        # Thermal throttling
        if self.thermal_state == "warm":
            budget *= 0.7
        elif self.thermal_state == "hot":
            budget *= 0.3
        elif self.thermal_state == "critical":
            budget *= 0.1
        
        # WiFi quality
        budget *= self.wifi_strength
        
        return budget
    
    @property
    def inference_speed(self) -> float:
        """Estimated tokens/sec based on hardware."""
        base_speed = 0.0
        
        if self.npu_chip == NPUChip.APPLE_NEURAL_ENGINE:
            base_speed = 30.0  # ~30 tok/s on A17 Pro
        elif self.npu_chip == NPUChip.QUALCOMM_HEXAGON:
            base_speed = 25.0  # ~25 tok/s on Snapdragon 8 Gen 3
        elif self.npu_chip == NPUChip.MEDIATEK_APU:
            base_speed = 20.0
        elif self.npu_chip == NPUChip.GOOGLE_TENSOR:
            base_speed = 15.0
        
        return base_speed * self.compute_budget


@dataclass
class MobileTask:
    """A task for mobile compute."""
    task_id: str
    task_type: str  # "inference", "embedding", "classification", "extraction"
    prompt: str
    model: str = "small"
    priority: int = 5  # 1-10, 10 = highest
    max_latency_ms: float = 5000.0
    created_at: float = 0.0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
    
    def to_dict(self) -> Dict:
        return asdict(self)


class MobileNode:
    """Mobile device as a compute node in the mesh."""
    
    def __init__(self, device_type: DeviceType = DeviceType.PHONE):
        self.node_id = self._generate_node_id()
        self.device_type = device_type
        self.capability = self._detect_capability()
        self.connected = False
        self.mesh_endpoint = None
        self.task_queue: List[MobileTask] = []
        self.completed_tasks: List[Dict] = []
        
    def _generate_node_id(self) -> str:
        """Generate unique node ID."""
        hostname = socket.gethostname()
        mac = hex(uuid.getnode())
        return f"mobile-{hostname[:8]}-{mac[-4:]}"
    
    def _detect_capability(self) -> MobileCapability:
        """Detect device capabilities."""
        system = platform.system()
        
        # Default capabilities
        capability = MobileCapability(
            device_type=self.device_type,
            ram_gb=4.0,
            storage_gb=64.0
        )
        
        # Detect based on platform
        if system == "Darwin":
            # iOS/macOS
            capability.npu_chip = NPUChip.APPLE_NEURAL_ENGINE
            capability.npu_tops = 18.0  # A17 Pro
            capability.gpu_tops = 2.0
            capability.ram_gb = 8.0
            capability.supported_models = ["llama-3.2-1b", "phi-3-mini"]
        elif system == "Android" or system == "Linux":
            # Android/Linux
            capability.npu_chip = NPUChip.QUALCOMM_HEXAGON
            capability.npu_tops = 15.0
            capability.gpu_tops = 1.5
            capability.ram_gb = 6.0
            capability.supported_models = ["llama-3.2-1b", "phi-3-mini"]
        else:
            # Unknown
            capability.supported_models = ["llama-3.2-1b"]
        
        return capability
    
    def start(self):
        """Start mobile node."""
        self.connected = True
        print(f"[Mobile] Node {self.node_id} started")
        print(f"[Mobile] Device: {self.device_type.value}")
        print(f"[Mobile] NPU: {self.capability.npu_chip.value} ({self.capability.npu_tops} TOPS)")
        print(f"[Mobile] RAM: {self.capability.ram_gb} GB")
        print(f"[Mobile] Inference: {self.capability.inference_speed:.1f} tok/s")
        print(f"[Mobile] Compute budget: {self.capability.compute_budget:.1%}")
    
    def stop(self):
        """Stop mobile node."""
        self.connected = False
        print(f"[Mobile] Node {self.node_id} stopped")
    
    def submit_task(self, task: MobileTask) -> bool:
        """Submit a task for processing."""
        if not self.connected:
            return False
        
        # Check if we can handle it
        if task.task_type == "inference":
            if self.capability.inference_speed < 1.0:
                return False
        
        self.task_queue.append(task)
        return True
    
    def process_task(self, task: MobileTask) -> Dict:
        """Process a task."""
        start_time = time.time()
        
        # Simulate processing
        result = {
            "task_id": task.task_id,
            "node_id": self.node_id,
            "status": "completed",
            "result": f"Processed: {task.prompt[:50]}...",
            "latency_ms": (time.time() - start_time) * 1000,
            "tokens_per_sec": self.capability.inference_speed
        }
        
        self.completed_tasks.append(result)
        return result
    
    def get_status(self) -> Dict:
        """Get node status."""
        return {
            "node_id": self.node_id,
            "device_type": self.device_type.value,
            "connected": self.connected,
            "capability": self.capability.to_dict(),
            "compute_budget": self.capability.compute_budget,
            "inference_speed": self.capability.inference_speed,
            "tasks_queued": len(self.task_queue),
            "tasks_completed": len(self.completed_tasks)
        }


class MobileMeshManager:
    """Manager for mobile nodes in the mesh."""
    
    def __init__(self):
        self.nodes: Dict[str, MobileNode] = {}
        self.discovery_port = 5354
    
    def register_node(self, node: MobileNode):
        """Register a mobile node."""
        self.nodes[node.node_id] = node
        print(f"[MobileMesh] Registered: {node.node_id} ({node.device_type.value})")
    
    def unregister_node(self, node_id: str):
        """Unregister a mobile node."""
        if node_id in self.nodes:
            del self.nodes[node_id]
            print(f"[MobileMesh] Unregistered: {node_id}")
    
    def get_best_node(self, task_type: str = "inference") -> Optional[MobileNode]:
        """Get the best available node for a task."""
        available = [
            node for node in self.nodes.values()
            if node.connected and node.capability.compute_budget > 0.3
        ]
        
        if not available:
            return None
        
        # Sort by inference speed and compute budget
        available.sort(
            key=lambda n: n.capability.inference_speed * n.capability.compute_budget,
            reverse=True
        )
        
        return available[0]
    
    def distribute_task(self, task: MobileTask) -> Optional[MobileNode]:
        """Distribute task to best available node."""
        node = self.get_best_node(task.task_type)
        if node and node.submit_task(task):
            return node
        return None
    
    def get_status(self) -> Dict:
        """Get manager status."""
        return {
            "total_nodes": len(self.nodes),
            "connected_nodes": sum(1 for n in self.nodes.values() if n.connected),
            "nodes": {
                node_id: node.get_status()
                for node_id, node in self.nodes.items()
            }
        }


def create_mobile_node(device_type: DeviceType = DeviceType.PHONE) -> MobileNode:
    """Create a mobile node."""
    return MobileNode(device_type)


def create_mobile_mesh_manager() -> MobileMeshManager:
    """Create a mobile mesh manager."""
    return MobileMeshManager()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="GlacierEQ Mobile Compute Node")
    parser.add_argument("--device", choices=["phone", "tablet", "watch"], default="phone")
    parser.add_argument("--status", action="store_true", help="Show status")
    args = parser.parse_args()
    
    device_type = DeviceType(args.device)
    node = create_mobile_node(device_type)
    
    if args.status:
        print(json.dumps(node.get_status(), indent=2))
    else:
        node.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            node.stop()
