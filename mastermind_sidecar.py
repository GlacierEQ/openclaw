#!/usr/bin/env python3
"""
APEX Highway Sidecar Node — openclaw
"""
import sys
import json
import time

def get_node_status():
    return {
        "node_id": "openclaw",
        "status": "HEALTHY",
        "latency_ms": 1.2,
        "timestamp": time.time()
    }

if __name__ == "__main__":
    print(json.dumps(get_node_status()))
