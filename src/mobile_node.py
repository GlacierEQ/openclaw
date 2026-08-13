#!/usr/bin/env python3
"""Truth-bounded mobile compute node for OpenClaw.

Capabilities are reported only when observed or explicitly configured. Tasks are
completed only by registered handlers; the module never fabricates model output
or hardware throughput from an operating-system name.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class DeviceType(Enum):
    PHONE = "phone"
    TABLET = "tablet"
    WATCH = "watch"
    HEADPHONE = "headphone"
    TV = "tv"
    CAR = "car"
    IOT = "iot"
    COMPUTER = "computer"


class NPUChip(Enum):
    APPLE_NEURAL_ENGINE = "ane"
    QUALCOMM_HEXAGON = "hexagon"
    MEDIATEK_APU = "apu"
    SAMSUNG_NPU = "samsung_npu"
    GOOGLE_TENSOR = "tensor"
    UNKNOWN = "unknown"


@dataclass
class MobileCapability:
    device_type: DeviceType
    platform_name: str
    machine: str
    npu_chip: NPUChip = NPUChip.UNKNOWN
    npu_tops: Optional[float] = None
    ram_gb: Optional[float] = None
    battery_percent: Optional[float] = None
    is_charging: Optional[bool] = None
    thermal_state: str = "unknown"
    measured_inference_tps: Optional[float] = None
    supported_models: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["device_type"] = self.device_type.value
        data["npu_chip"] = self.npu_chip.value
        return data

    @property
    def compute_budget(self) -> Optional[float]:
        if self.battery_percent is None and self.thermal_state == "unknown":
            return None
        budget = 1.0
        if self.battery_percent is not None:
            if self.battery_percent < 20:
                budget *= 0.2
            elif self.battery_percent < 50:
                budget *= 0.5
        if self.is_charging is True:
            budget *= 1.25
        budget *= {"normal": 1.0, "warm": 0.7, "hot": 0.3, "critical": 0.1, "unknown": 1.0}.get(self.thermal_state, 1.0)
        return max(0.0, min(1.25, budget))


@dataclass
class MobileTask:
    task_id: str
    task_type: str
    prompt: str
    model: str = ""
    priority: int = 5
    max_latency_ms: float = 30000.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


TaskHandler = Callable[[MobileTask], Dict[str, Any]]


def _memory_gb() -> Optional[float]:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((pages * page_size) / (1024**3), 2)
    except (ValueError, OSError, AttributeError):
        return None


def _optional_float(env: str) -> Optional[float]:
    value = os.getenv(env)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_bool(env: str) -> Optional[bool]:
    value = os.getenv(env)
    if value is None or value == "":
        return None
    return value.lower() in {"1", "true", "yes", "on"}


class MobileNode:
    def __init__(self, device_type: DeviceType = DeviceType.PHONE, *, node_id: Optional[str] = None):
        self.node_id = node_id or f"mobile-{socket.gethostname()[:12]}-{uuid.uuid4().hex[:8]}"
        self.device_type = device_type
        self.capability = self._detect_capability()
        self.connected = False
        self.task_queue: List[MobileTask] = []
        self.completed_tasks: List[Dict[str, Any]] = []
        self.handlers: Dict[str, TaskHandler] = {}
        self._register_configured_handlers()

    def _detect_capability(self) -> MobileCapability:
        chip_name = os.getenv("OPENCLAW_MOBILE_NPU", "unknown").lower()
        try:
            chip = NPUChip(chip_name)
        except ValueError:
            chip = NPUChip.UNKNOWN
        models = [item.strip() for item in os.getenv("OPENCLAW_MOBILE_MODELS", "").split(",") if item.strip()]
        return MobileCapability(
            device_type=self.device_type,
            platform_name=platform.system(),
            machine=platform.machine(),
            npu_chip=chip,
            npu_tops=_optional_float("OPENCLAW_MOBILE_NPU_TOPS"),
            ram_gb=_memory_gb(),
            battery_percent=_optional_float("OPENCLAW_MOBILE_BATTERY_PERCENT"),
            is_charging=_optional_bool("OPENCLAW_MOBILE_CHARGING"),
            thermal_state=os.getenv("OPENCLAW_MOBILE_THERMAL_STATE", "unknown").lower(),
            measured_inference_tps=_optional_float("OPENCLAW_MOBILE_INFERENCE_TPS"),
            supported_models=models,
        )

    def _register_configured_handlers(self) -> None:
        endpoint = os.getenv("OPENCLAW_MOBILE_OLLAMA_URL", "").rstrip("/")
        if endpoint:
            self.register_handler("inference", self._ollama_handler(endpoint))

    @staticmethod
    def _ollama_handler(endpoint: str) -> TaskHandler:
        def handle(task: MobileTask) -> Dict[str, Any]:
            model = task.model or os.getenv("OPENCLAW_MOBILE_DEFAULT_MODEL", "")
            if not model:
                return {"status": "FAILED", "error": "MODEL_NOT_CONFIGURED"}
            body = json.dumps({"model": model, "prompt": task.prompt, "stream": False}).encode("utf-8")
            request = urllib.request.Request(
                f"{endpoint}/api/generate",
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "OpenClaw-Mobile/3.1"},
                method="POST",
            )
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=max(1.0, task.max_latency_ms / 1000.0)) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
                return {"status": "FAILED", "error": str(exc), "latency_ms": (time.perf_counter() - started) * 1000.0}
            text = str(payload.get("response", ""))
            if not text.strip():
                return {"status": "FAILED", "error": "EMPTY_RESPONSE", "latency_ms": (time.perf_counter() - started) * 1000.0}
            return {
                "status": "COMPLETED",
                "response": text,
                "model": model,
                "latency_ms": (time.perf_counter() - started) * 1000.0,
                "eval_count": payload.get("eval_count"),
                "eval_duration": payload.get("eval_duration"),
            }
        return handle

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        if not task_type or not callable(handler):
            raise ValueError("task_type and callable handler are required")
        self.handlers[task_type] = handler

    def start(self) -> None:
        self.connected = True

    def stop(self) -> None:
        self.connected = False

    def submit_task(self, task: MobileTask) -> bool:
        if not self.connected or task.task_type not in self.handlers:
            return False
        self.task_queue.append(task)
        self.task_queue.sort(key=lambda item: (-item.priority, item.created_at))
        return True

    def process_task(self, task: MobileTask) -> Dict[str, Any]:
        if not self.connected:
            return {"task_id": task.task_id, "node_id": self.node_id, "status": "REJECTED", "error": "NODE_NOT_RUNNING"}
        handler = self.handlers.get(task.task_type)
        if handler is None:
            return {"task_id": task.task_id, "node_id": self.node_id, "status": "UNSUPPORTED", "error": "NO_TASK_HANDLER"}
        started = time.perf_counter()
        try:
            result = dict(handler(task))
        except Exception as exc:
            result = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
        result.setdefault("latency_ms", (time.perf_counter() - started) * 1000.0)
        result["task_id"] = task.task_id
        result["node_id"] = self.node_id
        if result.get("status") == "COMPLETED":
            self.completed_tasks.append(result)
        return result

    def process_next(self) -> Optional[Dict[str, Any]]:
        if not self.task_queue:
            return None
        task = self.task_queue.pop(0)
        return self.process_task(task)

    def get_status(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "device_type": self.device_type.value,
            "running": self.connected,
            "capability": self.capability.to_dict(),
            "compute_budget": self.capability.compute_budget,
            "registered_handlers": sorted(self.handlers),
            "tasks_queued": len(self.task_queue),
            "tasks_completed": len(self.completed_tasks),
            "claim": "OBSERVED_OR_OPERATOR_CONFIGURED_CAPABILITIES_ONLY",
        }


class MobileMeshManager:
    def __init__(self):
        self.nodes: Dict[str, MobileNode] = {}

    def register_node(self, node: MobileNode) -> None:
        self.nodes[node.node_id] = node

    def unregister_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)

    def get_best_node(self, task_type: str = "inference") -> Optional[MobileNode]:
        candidates = [node for node in self.nodes.values() if node.connected and task_type in node.handlers]
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda node: (
                node.capability.measured_inference_tps or 0.0,
                node.capability.ram_gb or 0.0,
                node.node_id,
            ),
            reverse=True,
        )[0]

    def distribute_task(self, task: MobileTask) -> Optional[MobileNode]:
        node = self.get_best_node(task.task_type)
        return node if node and node.submit_task(task) else None

    def get_status(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "running_nodes": sum(node.connected for node in self.nodes.values()),
            "nodes": {node_id: node.get_status() for node_id, node in self.nodes.items()},
        }


def create_mobile_node(device_type: DeviceType = DeviceType.PHONE) -> MobileNode:
    return MobileNode(device_type)


def create_mobile_mesh_manager() -> MobileMeshManager:
    return MobileMeshManager()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OpenClaw mobile compute node")
    parser.add_argument("--device", choices=[item.value for item in DeviceType], default="phone")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    node = MobileNode(DeviceType(args.device))
    if args.status:
        print(json.dumps(node.get_status(), indent=2, sort_keys=True))
    else:
        node.start()
        print(json.dumps(node.get_status(), indent=2, sort_keys=True))
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            node.stop()
