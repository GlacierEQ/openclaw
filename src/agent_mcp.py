"""MCP server exposing the OpenClaw free-agent fabric."""
from __future__ import annotations

import hmac
import json
import os
import sys
from typing import Any, Dict, Optional

from .agent_runtime import RuntimeAgentHub


class AgentFabricMCP:
    def __init__(self, hub: Optional[RuntimeAgentHub] = None):
        self.hub = hub or RuntimeAgentHub()

    @staticmethod
    def _text(value: Any, is_error: bool = False) -> Dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(value, indent=2, sort_keys=True, default=str)}], "isError": is_error}

    def tools(self):
        return [
            {"name": "openclaw_agents_discover", "description": "Discover all currently reachable/free model endpoints, including every installed Ollama model.", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "openclaw_agents_list", "description": "List OpenClaw model endpoints.", "inputSchema": {"type": "object", "properties": {"filter": {"type": "string", "enum": ["all", "free", "local", "verified"]}}}},
            {"name": "openclaw_agents_test", "description": "Probe one endpoint or all endpoints.", "inputSchema": {"type": "object", "properties": {"agent": {"type": "string"}}}},
            {"name": "openclaw_agents_query", "description": "Run a prompt on one named endpoint.", "inputSchema": {"type": "object", "properties": {"agent": {"type": "string"}, "prompt": {"type": "string"}, "mode": {"type": "string"}}, "required": ["agent", "prompt"]}},
            {"name": "openclaw_agents_route", "description": "Run a prompt through free-first fallback routing until a model answers.", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "prefer_local": {"type": "boolean"}, "mode": {"type": "string"}}, "required": ["prompt"]}},
            {"name": "openclaw_agents_fanout", "description": "Run one prompt across multiple free endpoints concurrently.", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "max_agents": {"type": "integer", "minimum": 0}, "mode": {"type": "string"}}, "required": ["prompt"]}},
            {"name": "openclaw_agents_report", "description": "Return current provider, free, local, and verified endpoint counts.", "inputSchema": {"type": "object", "properties": {}}},
        ]

    def call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == "openclaw_agents_discover":
            agents = self.hub.discover()
            return self._text({"count": len(agents), "report": self.hub.get_report(), "agents": agents})
        if name == "openclaw_agents_list":
            filter_type = args.get("filter", "all")
            if filter_type == "free":
                agents = self.hub.get_free_agents()
            elif filter_type == "local":
                agents = self.hub.get_local_agents()
            elif filter_type == "verified":
                agents = self.hub.get_verified_agents()
            else:
                agents = [endpoint.to_dict() for endpoint in self.hub.agents.values()]
            return self._text({"count": len(agents), "agents": agents})
        if name == "openclaw_agents_test":
            agent = args.get("agent")
            return self._text(self.hub.test_agent(str(agent)) if agent else self.hub.test_all())
        if name == "openclaw_agents_query":
            result = self.hub.query(str(args.get("agent", "")), str(args.get("prompt", "")), mode=str(args.get("mode", "code")))
            return self._text(result, result.get("status") != "completed")
        if name == "openclaw_agents_route":
            result = self.hub.route_query(str(args.get("prompt", "")), prefer_local=bool(args.get("prefer_local", True)), mode=str(args.get("mode", "code")))
            return self._text(result, result.get("status") != "completed")
        if name == "openclaw_agents_fanout":
            result = self.hub.fanout(str(args.get("prompt", "")), max_agents=int(args.get("max_agents", 0)), mode=str(args.get("mode", "plan")))
            return self._text(result, result.get("status") != "completed")
        if name == "openclaw_agents_report":
            return self._text(self.hub.get_report())
        return self._text({"status": "failed", "error": "UNKNOWN_TOOL", "tool": name}, True)

    def handle(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = request.get("method")
        req_id = request.get("id")
        params = request.get("params") or {}
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "openclaw-agent-fabric", "version": "3.2.0"}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.tools()}}
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": req_id, "result": self.call(str(params.get("name", "")), params.get("arguments") or {})}
        if req_id is None:
            return None
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown method: {method}"}}

    def run_stdio(self) -> None:
        for raw in sys.stdin:
            if not raw.strip():
                continue
            try:
                response = self.handle(json.loads(raw))
                if response is not None:
                    print(json.dumps(response, separators=(",", ":")), flush=True)
            except Exception as exc:
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}, separators=(",", ":")), flush=True)


def create_http_app(server: Optional[AgentFabricMCP] = None):
    from fastapi import FastAPI, Header, HTTPException

    server = server or AgentFabricMCP()
    app = FastAPI(title="OpenClaw Agent Fabric MCP", version="3.2.0")

    @app.get("/health")
    def health():
        return {"status": "healthy", "agents": server.hub.get_report()}

    @app.post("/mcp")
    def mcp(request: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
        expected = os.getenv("OPENCLAW_MCP_TOKEN", "")
        if expected:
            scheme, _, supplied = (authorization or "").partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(supplied, expected):
                raise HTTPException(status_code=401, detail="invalid bearer token")
        return server.handle(request) or {"jsonrpc": "2.0", "result": None}

    return app


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="openclaw-agent-mcp")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stdio", action="store_true")
    mode.add_argument("--http", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    server = AgentFabricMCP()
    if args.http:
        import uvicorn
        uvicorn.run(create_http_app(server), host=args.host, port=args.port)
    else:
        server.run_stdio()


if __name__ == "__main__":
    main()
