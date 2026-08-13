#!/usr/bin/env python3
"""OpenClaw REST control plane with authenticated mutation endpoints."""
from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.integrity import WatchdogDaemon
from src.openclaw import OpenClawEngine


class ActionRequest(BaseModel):
    action_type: str
    target: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    coords: Optional[Tuple[int, int]] = None
    principal: str = "api-operator"
    source: str = "rest"
    idempotency_key: Optional[str] = None
    human_approved: bool = False


class VisionRequest(BaseModel):
    viewport: Tuple[int, int] = (1920, 1080)


class WatchRequest(BaseModel):
    directory: str


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    return value if scheme.lower() == "bearer" and value else None


def create_app(*, engine: Optional[OpenClawEngine] = None, daemon: Optional[WatchdogDaemon] = None, watch_dirs: Optional[List[str]] = None, require_token: Optional[bool] = None) -> FastAPI:
    engine = engine or OpenClawEngine()
    daemon = daemon or WatchdogDaemon(watch_dirs=watch_dirs or ["."])
    if not daemon.fingerprints:
        daemon.initial_scan()
    api_cfg = engine.config.get("api", {})
    token_required = bool(api_cfg.get("require_token", True)) if require_token is None else bool(require_token)
    token_env = str(api_cfg.get("token_env", "OPENCLAW_API_TOKEN"))

    app = FastAPI(title="OpenClaw", version=str(engine.config.get("version", "3.1.0")))
    app.state.engine = engine
    app.state.daemon = daemon
    app.state.require_token = token_required
    app.state.token_env = token_env

    def authorize_mutation(authorization: Optional[str] = Header(default=None)) -> None:
        if not app.state.require_token:
            return
        expected = os.getenv(app.state.token_env, "")
        if not expected:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{app.state.token_env} not configured")
        supplied = _bearer_token(authorization)
        if supplied is None or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"service": "openclaw-api", "engine": app.state.engine.health(), "integrity": app.state.daemon.get_report(), "mutation_auth_required": app.state.require_token}

    @app.get("/integrity/status")
    def integrity_status() -> Dict[str, Any]:
        return app.state.daemon.get_report()

    @app.post("/integrity/check")
    def integrity_check(_: None = Depends(authorize_mutation)) -> Dict[str, Any]:
        return app.state.daemon.check_integrity()

    @app.post("/integrity/scan")
    def integrity_scan(_: None = Depends(authorize_mutation)) -> Dict[str, Any]:
        return app.state.daemon.initial_scan()

    @app.post("/integrity/add-watch")
    def add_watch(body: WatchRequest, _: None = Depends(authorize_mutation)) -> Dict[str, Any]:
        path = Path(body.directory).expanduser().resolve()
        if path in app.state.daemon.watch_dirs:
            return {"status": "already_watching", "directory": str(path)}
        if not path.exists() or not path.is_dir():
            raise HTTPException(status_code=400, detail="directory does not exist")
        app.state.daemon.watch_dirs.append(path)
        return {"status": "added", "directory": str(path)}

    @app.get("/engine/history")
    def engine_history(limit: int = 50) -> Dict[str, Any]:
        history = app.state.engine.get_audit_trail(max(1, min(int(limit), 1000)))
        return {"total_returned": len(history), "actions": history}

    @app.get("/engine/stats")
    def engine_stats() -> Dict[str, Any]:
        return app.state.engine.health()

    @app.post("/engine/action")
    def engine_action(body: ActionRequest, _: None = Depends(authorize_mutation)) -> Dict[str, Any]:
        result = app.state.engine.execute_action(action_type=body.action_type, target=body.target, parameters=body.parameters, coords=body.coords, principal=body.principal, source=body.source, idempotency_key=body.idempotency_key, human_approved=body.human_approved)
        code = {"OPENCLAW_BACKEND_UNAVAILABLE": 503, "RATE_LIMITED": 429, "DENIED_BY_AKOS_POLICY": 403, "HUMAN_APPROVAL_REQUIRED": 403, "UNSUPPORTED_BY_BACKEND": 403, "OPENCLAW_ACTION_FAILED": 502}.get(result.get("status"))
        if code:
            raise HTTPException(status_code=code, detail=result)
        return result

    @app.post("/engine/vision")
    def engine_vision(body: VisionRequest, _: None = Depends(authorize_mutation)) -> Dict[str, Any]:
        return app.state.engine.sample_vision_state(body.viewport)

    return app


app = create_app()


def main() -> None:
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="OpenClaw API server")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--watch-dir", action="append", dest="watch_dirs")
    args = parser.parse_args()
    if args.watch_dirs:
        app.state.daemon = WatchdogDaemon(watch_dirs=args.watch_dirs)
        app.state.daemon.initial_scan()
    cfg = app.state.engine.config.get("api", {})
    uvicorn.run(app, host=args.host or str(cfg.get("host", "127.0.0.1")), port=args.port or int(cfg.get("port", 8088)))


if __name__ == "__main__":
    main()
