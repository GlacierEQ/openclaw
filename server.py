#!/usr/bin/env python3
"""OpenClaw API Server — REST API for file integrity monitoring and action governance."""

import json
import time
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any
import hashlib

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / ".integrity"))
from watchdog_daemon import WatchdogDaemon
from src.openclaw import OpenClawEngine

HOST = "0.0.0.0"
PORT = 8088


class OpenClawAPI(BaseHTTPRequestHandler):
    """REST API handler for OpenClaw services."""

    daemon: WatchdogDaemon = None
    engine: OpenClawEngine = None

    def _send_json(self, data: Dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _read_body(self) -> Dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/health":
            self._send_json({
                "status": "healthy",
                "service": "openclaw-api",
                "version": "3.0.0",
                "timestamp": time.time(),
            })

        elif path == "/integrity/status":
            report = self.daemon.get_report()
            self._send_json(report)

        elif path == "/integrity/check":
            result = self.daemon.check_integrity()
            self._send_json(result)

        elif path == "/integrity/scan":
            result = self.daemon.initial_scan()
            self._send_json(result)

        elif path == "/engine/history":
            history = self.engine.get_audit_trail()
            self._send_json({
                "total_actions": len(history),
                "actions": history[-50:],
            })

        elif path == "/engine/stats":
            self._send_json({
                "agent_id": self.engine.agent_id,
                "total_actions": len(self.engine.action_history),
                "config": self.engine.config.get("openclaw_version", "unknown"),
            })

        else:
            self._send_json({"error": "Not found", "endpoints": [
                "/health", "/integrity/status", "/integrity/check",
                "/integrity/scan", "/engine/history", "/engine/stats",
                "/engine/action (POST)", "/engine/vision (POST)",
            ]}, 404)

    def do_POST(self):
        path = self.path.rstrip("/")

        if path == "/engine/action":
            body = self._read_body()
            result = self.engine.execute_action(
                action_type=body.get("action_type", "click"),
                target=body.get("target", ""),
                parameters=body.get("parameters"),
                coords=tuple(body.get("coords", [0, 0])),
            )
            self._send_json(result)

        elif path == "/engine/vision":
            body = self._read_body()
            result = self.engine.sample_vision_state(
                viewport=tuple(body.get("viewport", [1920, 1080]))
            )
            self._send_json(result)

        elif path == "/integrity/add-watch":
            body = self._read_body()
            dir_path = body.get("directory", ".")
            if dir_path not in self.daemon.watch_dirs:
                from pathlib import Path as P
                self.daemon.watch_dirs.append(P(dir_path).resolve())
                self._send_json({"status": "added", "directory": dir_path})
            else:
                self._send_json({"status": "already_watching", "directory": dir_path})

        else:
            self._send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        print(f"[OpenClaw API] {args[0]}" if args else "")


def create_server(host: str = HOST, port: int = PORT) -> HTTPServer:
    OpenClawAPI.daemon = WatchdogDaemon(watch_dirs=["."])
    OpenClawAPI.daemon.initial_scan()
    OpenClawAPI.engine = OpenClawEngine()

    server = HTTPServer((host, port), OpenClawAPI)
    print(f"[OpenClaw API] Server running on http://{host}:{port}")
    return server


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw API Server")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OpenClaw API] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
