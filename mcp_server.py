#!/usr/bin/env python3
"""OpenClaw MCP JSON-RPC server for stdio or authenticated HTTP."""
from __future__ import annotations
import hmac, json, os, sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.integrity import WatchdogDaemon
from src.openclaw import OpenClawEngine
from src.agent_hub import FreeTierAgentHub

class OpenClawMCPServer:
    def __init__(self, *, engine=None, daemon=None, agent_hub=None):
        self.daemon = daemon or WatchdogDaemon(watch_dirs=["."])
        self.engine = engine or OpenClawEngine()
        self.agent_hub = agent_hub or FreeTierAgentHub()
        self.tools = self._register_tools()

    def _register_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name":"openclaw_audit_integrity","description":"Audit monitored directories against the persistent SHA-256 baseline.","inputSchema":{"type":"object","properties":{"directories":{"type":"array","items":{"type":"string"}}}}},
            {"name":"openclaw_scan_directory","description":"Create a SHA-256 baseline for supplied directories.","inputSchema":{"type":"object","properties":{"directories":{"type":"array","items":{"type":"string"}}},"required":["directories"]}},
            {"name":"openclaw_execute_action","description":"Run a policy-governed computer-user action; execution is reported only with a real backend receipt.","inputSchema":{"type":"object","properties":{"action_type":{"type":"string"},"target":{"type":"string"},"parameters":{"type":"object"},"coords":{"type":"array","items":{"type":"integer"},"minItems":2,"maxItems":2},"principal":{"type":"string"},"idempotency_key":{"type":"string"},"human_approved":{"type":"boolean"}},"required":["action_type"]}},
            {"name":"openclaw_get_audit_trail","description":"Return persisted hash-chained action records.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":1000}}}},
            {"name":"openclaw_verify_audit_trail","description":"Verify the SHA-256/HMAC audit chain.","inputSchema":{"type":"object","properties":{}}},
            {"name":"openclaw_vision_sample","description":"Capture a backend viewport sample when available.","inputSchema":{"type":"object","properties":{"viewport":{"type":"array","items":{"type":"integer"},"minItems":2,"maxItems":2}}}},
            {"name":"openclaw_list_agents","description":"List configured agent routes and observed state.","inputSchema":{"type":"object","properties":{"filter":{"type":"string","enum":["all","verified","free","local"]}}}},
            {"name":"openclaw_test_agents","description":"Probe configured agents.","inputSchema":{"type":"object","properties":{}}},
            {"name":"openclaw_query_agent","description":"Query a named configured agent.","inputSchema":{"type":"object","properties":{"agent_name":{"type":"string"},"prompt":{"type":"string"},"system":{"type":"string"}},"required":["agent_name","prompt"]}},
            {"name":"openclaw_route_query","description":"Route a query to an observed verified agent.","inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"prefer_free":{"type":"boolean"}},"required":["prompt"]}},
            {"name":"openclaw_get_agent_report","description":"Get agent counts.","inputSchema":{"type":"object","properties":{}}},
            {"name":"openclaw_health_check","description":"Return runtime, integrity, backend, audit, and agent health.","inputSchema":{"type":"object","properties":{}}},
        ]

    @staticmethod
    def _text(value: Any, *, is_error=False):
        return {"content":[{"type":"text","text":json.dumps(value,indent=2,sort_keys=True,default=str)}],"isError":is_error}

    def handle_request(self, request: Dict[str, Any]):
        if request.get("jsonrpc") not in {None,"2.0"}:
            return {"jsonrpc":"2.0","id":request.get("id"),"error":{"code":-32600,"message":"invalid jsonrpc version"}}
        method=request.get("method"); params=request.get("params") or {}; req_id=request.get("id")
        if method=="notifications/initialized": return None
        if method=="initialize":
            return {"jsonrpc":"2.0","id":req_id,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"glaciereq-openclaw","version":str(self.engine.config.get("version","3.1.0"))}}}
        if method=="tools/list": return {"jsonrpc":"2.0","id":req_id,"result":{"tools":self.tools}}
        if method=="tools/call":
            try: result=self._call_tool(str(params.get("name","")),params.get("arguments") or {})
            except Exception as exc: result=self._text({"status":"TOOL_ERROR","error":f"{type(exc).__name__}: {exc}"},is_error=True)
            return {"jsonrpc":"2.0","id":req_id,"result":result}
        if req_id is None: return None
        return {"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":f"unknown method: {method}"}}

    def _call_tool(self,name,args):
        if name=="openclaw_audit_integrity":
            if args.get("directories"): self.daemon.watch_dirs=[Path(d).expanduser().resolve() for d in args["directories"]]
            return self._text(self.daemon.check_integrity())
        if name=="openclaw_scan_directory":
            self.daemon.watch_dirs=[Path(d).expanduser().resolve() for d in (args.get("directories") or ["."])]
            return self._text(self.daemon.initial_scan())
        if name=="openclaw_execute_action":
            coords=args.get("coords")
            result=self.engine.execute_action(str(args.get("action_type","")),str(args.get("target","")),args.get("parameters") or {},tuple(coords) if isinstance(coords,list) and len(coords)==2 else None,principal=str(args.get("principal","mcp-operator")),source="mcp",idempotency_key=args.get("idempotency_key"),human_approved=bool(args.get("human_approved",False)))
            return self._text(result,is_error=result.get("status") not in {"OPENCLAW_ACTION_EXECUTED","OPENCLAW_ACTION_PLANNED","OPENCLAW_ACTION_REPLAYED"})
        if name=="openclaw_get_audit_trail": return self._text(self.engine.get_audit_trail(max(1,min(int(args.get("limit",50)),1000))))
        if name=="openclaw_verify_audit_trail": return self._text(self.engine.verify_audit_trail())
        if name=="openclaw_vision_sample": return self._text(self.engine.sample_vision_state(tuple(args.get("viewport",[1920,1080]))))
        if name=="openclaw_list_agents":
            f=args.get("filter","all")
            agents=self.agent_hub.get_verified_agents() if f=="verified" else self.agent_hub.get_free_agents() if f=="free" else self.agent_hub.get_local_agents() if f=="local" else [a.to_dict() for a in self.agent_hub.agents.values()]
            return self._text({"agents":agents,"count":len(agents)})
        if name=="openclaw_test_agents": return self._text({"results":self.agent_hub.test_all(),"report":self.agent_hub.get_report()})
        if name=="openclaw_query_agent": return self._text(self.agent_hub.query(str(args.get("agent_name","")),str(args.get("prompt","")),str(args.get("system","You are a coding assistant."))))
        if name=="openclaw_route_query": return self._text(self.agent_hub.route_query(str(args.get("prompt","")),prefer_local=bool(args.get("prefer_free",True))))
        if name=="openclaw_get_agent_report": return self._text(self.agent_hub.get_report())
        if name=="openclaw_health_check": return self._text({"engine":self.engine.health(),"integrity":self.daemon.get_report(),"agents":self.agent_hub.get_report()})
        return self._text({"status":"UNKNOWN_TOOL","tool":name},is_error=True)

    def run_stdio(self):
        for raw in sys.stdin:
            if not raw.strip(): continue
            try:
                request=json.loads(raw); response=self.handle_request(request)
                if response is not None: print(json.dumps(response,separators=(",",":")),flush=True)
            except Exception as exc:
                print(json.dumps({"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":f"parse error: {exc}"}},separators=(",",":")),flush=True)

def create_http_app(server=None):
    from fastapi import FastAPI, Header, HTTPException
    server=server or OpenClawMCPServer(); app=FastAPI(title="OpenClaw MCP",version=str(server.engine.config.get("version","3.1.0")))
    cfg=server.engine.config.get("mcp",{}); token_env=str(cfg.get("token_env","OPENCLAW_MCP_TOKEN")); require_token=bool(cfg.get("require_token",True))
    @app.post("/mcp")
    def mcp(request:Dict[str,Any],authorization:Optional[str]=Header(default=None)):
        if require_token:
            expected=os.getenv(token_env,""); scheme,_,supplied=(authorization or "").partition(" ")
            if not expected: raise HTTPException(status_code=503,detail=f"{token_env} not configured")
            if scheme.lower()!="bearer" or not hmac.compare_digest(supplied,expected): raise HTTPException(status_code=401,detail="invalid bearer token")
        return server.handle_request(request) or {"jsonrpc":"2.0","result":None}
    @app.get("/health")
    def health(): return {"status":"healthy","engine":server.engine.health()}
    return app

def main():
    import argparse
    parser=argparse.ArgumentParser(description="OpenClaw MCP server"); mode=parser.add_mutually_exclusive_group(); mode.add_argument("--stdio",action="store_true"); mode.add_argument("--http",action="store_true"); parser.add_argument("--host",default="127.0.0.1"); parser.add_argument("--port",type=int,default=8089); args=parser.parse_args(); server=OpenClawMCPServer()
    if args.http:
        import uvicorn; uvicorn.run(create_http_app(server),host=args.host,port=args.port)
    else: server.run_stdio()

if __name__=="__main__": main()
