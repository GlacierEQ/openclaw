#!/usr/bin/env python3
"""OpenClaw MCP Server — Model Context Protocol integration for agent ecosystems."""

import json
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / ".integrity"))
from watchdog_daemon import WatchdogDaemon
from src.openclaw import OpenClawEngine


class OpenClawMCPServer:
    """MCP server exposing OpenClaw capabilities to AI agents."""

    def __init__(self):
        self.daemon = WatchdogDaemon(watch_dirs=["."])
        self.engine = OpenClawEngine()
        self.tools = self._register_tools()

    def _register_tools(self) -> List[Dict]:
        return [
            {
                "name": "openclaw_audit_integrity",
                "description": "Audit file integrity across monitored directories. Returns SHA-256 hash changes, additions, and deletions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "directories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional: specific directories to audit (default: all watched)"
                        }
                    }
                },
            },
            {
                "name": "openclaw_scan_directory",
                "description": "Perform initial SHA-256 scan of directories and store baseline fingerprints.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "directories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Directories to scan"
                        }
                    },
                    "required": ["directories"]
                },
            },
            {
                "name": "openclaw_execute_action",
                "description": "Execute a governed computer-user action (click, type, navigate, etc.) with cryptographic audit trail.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action_type": {"type": "string", "description": "Action type: click, type, scroll, navigate, screenshot, etc."},
                        "target": {"type": "string", "description": "Target element or URL"},
                        "parameters": {"type": "object", "description": "Action parameters"},
                        "coords": {"type": "array", "items": {"type": "number"}, "description": "X,Y coordinates for click actions"}
                    },
                    "required": ["action_type", "target"]
                },
            },
            {
                "name": "openclaw_get_audit_trail",
                "description": "Retrieve the full cryptographic action audit trail with SHA-256 signatures.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max events to return (default: 50)"}
                    }
                },
            },
            {
                "name": "openclaw_vision_sample",
                "description": "Sample viewport state via OCR/vision detection.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "viewport": {"type": "array", "items": {"type": "number"}, "description": "Width,Height (default: [1920,1080])"}
                    }
                },
            },
            {
                "name": "openclaw_health_check",
                "description": "Check OpenClaw service health and configuration status.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def handle_request(self, request: Dict) -> Dict:
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "openclaw-mcp", "version": "3.0.0"},
                },
            }

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.tools}}

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = self._call_tool(tool_name, arguments)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    def _call_tool(self, name: str, args: Dict) -> Dict:
        if name == "openclaw_audit_integrity":
            dirs = args.get("directories")
            if dirs:
                self.daemon.watch_dirs = [Path(d).resolve() for d in dirs]
            result = self.daemon.check_integrity()
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        elif name == "openclaw_scan_directory":
            dirs = args.get("directories", ["."])
            self.daemon.watch_dirs = [Path(d).resolve() for d in dirs]
            result = self.daemon.initial_scan()
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        elif name == "openclaw_execute_action":
            result = self.engine.execute_action(
                action_type=args.get("action_type", "click"),
                target=args.get("target", ""),
                parameters=args.get("parameters"),
                coords=tuple(args.get("coords", [0, 0])),
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        elif name == "openclaw_get_audit_trail":
            limit = args.get("limit", 50)
            history = self.engine.get_audit_trail()[-limit:]
            return {"content": [{"type": "text", "text": json.dumps(history, indent=2)}]}

        elif name == "openclaw_vision_sample":
            result = self.engine.sample_vision_state(
                viewport=tuple(args.get("viewport", [1920, 1080]))
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        elif name == "openclaw_health_check":
            return {"content": [{"type": "text", "text": json.dumps({
                "status": "healthy",
                "version": "3.0.0",
                "engine": self.engine.agent_id,
                "tracked_files": len(self.daemon.fingerprints),
                "timestamp": time.time(),
            }, indent=2)}]}

        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}]}

    def run_stdio(self):
        import sys
        print("[OpenClaw MCP] Server started on stdio", file=sys.stderr)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps(response))
                sys.stdout.flush()
            except json.JSONDecodeError:
                pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run on stdio (MCP default)")
    parser.add_argument("--port", type=int, default=8089, help="HTTP port for SSE mode")
    args = parser.parse_args()

    server = OpenClawMCPServer()
    if args.stdio:
        server.run_stdio()
    else:
        print(f"[OpenClaw MCP] HTTP mode on port {args.port}")
        server.run_stdio()


if __name__ == "__main__":
    main()
