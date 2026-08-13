#!/usr/bin/env python3
"""OpenClaw sidecar presence projection."""
import json
import time


def get_node_status():
    started = time.perf_counter()
    return {
        "node_id": "openclaw",
        "status": "PRESENT",
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "timestamp": time.time(),
        "claim": "PROCESS_LOCAL_PRESENCE_ONLY"
    }


if __name__ == "__main__":
    print(json.dumps(get_node_status(), sort_keys=True))
