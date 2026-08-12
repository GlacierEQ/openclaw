#!/usr/bin/env python3
"""OpenClaw MCP Server — Model Context Protocol integration for agent ecosystems."""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / ".integrity"))
from watchdog_daemon import WatchdogDaemon
from src.openclaw import OpenClawEngine
from src.agent_hub import FreeTierAgentHub


class OpenClawMCPServer:
    """MCP server exposing OpenClaw capabilities to AI agents."""

    def __init__(self):
        self.daemon = WatchdogDaemon(watch_dirs=["."])
        self.engine = OpenClawEngine()
        self.agent_hub = FreeTierAgentHub()
        self.tools = self._register_tools()

    def _register_tools(self) -> List[Dict]:
        return [
            # === File Integrity Tools ===
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
            # === Action Governance Tools ===
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
            # === Vision Tools ===
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
            # === Free Tier Agent Hub Tools ===
            {
                "name": "openclaw_list_agents",
                "description": "List all available free tier AI coding agents (Groq, Cline, Kilo, OpenCode, Aider, Continue, etc.).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filter": {"type": "string", "description": "Filter: 'verified', 'free', 'all'"}
                    }
                },
            },
            {
                "name": "openclaw_test_agents",
                "description": "Test all configured AI agents and return their status.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "openclaw_query_agent",
                "description": "Query a specific AI agent with a coding prompt.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_name": {"type": "string", "description": "Agent name (e.g., 'groq-llama3.3', 'cline-groq', 'kilo-groq')"},
                        "prompt": {"type": "string", "description": "The coding question or task"},
                        "system": {"type": "string", "description": "Optional system prompt"}
                    },
                    "required": ["agent_name", "prompt"]
                },
            },
            {
                "name": "openclaw_route_query",
                "description": "Automatically route a coding query to the best available free agent.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The coding question or task"},
                        "prefer_free": {"type": "boolean", "description": "Prefer free tier agents (default: true)"}
                    },
                    "required": ["prompt"]
                },
            },
            {
                "name": "openclaw_get_agent_report",
                "description": "Get status report of all agents (verified, failed, untested).",
                "inputSchema": {"type": "object", "properties": {}},
            },
            # === System Health ===
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
        # === File Integrity Tools ===
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

        # === Action Governance Tools ===
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

        # === Vision Tools ===
        elif name == "openclaw_vision_sample":
            result = self.engine.sample_vision_state(
                viewport=tuple(args.get("viewport", [1920, 1080]))
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        # === Agent Hub Tools ===
        elif name == "openclaw_list_agents":
            filter_type = args.get("filter", "all")
            if filter_type == "verified":
                agents = self.agent_hub.get_verified_agents()
            elif filter_type == "free":
                agents = self.agent_hub.get_free_agents()
            else:
                agents = [a.to_dict() for a in self.agent_hub.agents.values()]
            return {"content": [{"type": "text", "text": json.dumps({"agents": agents, "count": len(agents)}, indent=2)}]}

        elif name == "openclaw_test_agents":
            results = self.agent_hub.test_all()
            report = self.agent_hub.get_report()
            return {"content": [{"type": "text", "text": json.dumps({"results": results, "report": report}, indent=2)}]}

        elif name == "openclaw_query_agent":
            result = self.agent_hub.query(
                agent_name=args.get("agent_name", ""),
                prompt=args.get("prompt", ""),
                system=args.get("system", "You are a coding assistant. Respond concisely."),
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        elif name == "openclaw_route_query":
            result = self.agent_hub.route_query(
                prompt=args.get("prompt", ""),
                prefer_free=args.get("prefer_free", True),
            )
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        elif name == "openclaw_get_agent_report":
            report = self.agent_hub.get_report()
            return {"content": [{"type": "text", "text": json.dumps(report, indent=2)}]}

        # === System Health ===
        elif name == "openclaw_health_check":
            return {"content": [{"type": "text", "text": json.dumps({
                "status": "healthy",
                "version": "3.0.0",
                "engine": self.engine.agent_id,
                "tracked_files": len(self.daemon.fingerprints),
                "agents_verified": sum(1 for a in self.agent_hub.agents.values() if a.status == "verified"),
                "agents_total": len(self.agent_hub.agents),
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
