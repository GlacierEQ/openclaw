#!/usr/bin/env python3
"""OpenClaw command-line interface."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.action_runtime import DryRunBackend
from src.agent_runtime import RuntimeAgentHub
from src.integrity import WatchdogDaemon
from src.openclaw import OpenClawEngine


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def cmd_scan(args):
    emit(WatchdogDaemon(args.dirs).initial_scan())


def cmd_check(args):
    emit(WatchdogDaemon(args.dirs).check_integrity())


def cmd_daemon(args):
    daemon = WatchdogDaemon(args.dirs, poll_interval=args.interval)
    daemon.initial_scan()
    daemon.run_daemon()


def cmd_action(args):
    params: Dict[str, Any] = json.loads(args.params_json) if args.params_json else {}
    coords = (args.x, args.y) if args.x is not None and args.y is not None else None
    engine = OpenClawEngine(backend=DryRunBackend() if args.dry_run else None)
    emit(engine.execute_action(
        args.type,
        args.target,
        params,
        coords,
        principal=args.principal,
        source="cli",
        idempotency_key=args.idempotency_key,
        human_approved=args.human_approved,
    ))


def cmd_audit(args):
    engine = OpenClawEngine()
    emit(engine.verify_audit_trail() if args.verify else engine.get_audit_trail(args.limit))


def cmd_report(args):
    emit(WatchdogDaemon(args.dirs).get_report())


def cmd_doctor(args):
    emit(OpenClawEngine().health())


def cmd_serve(args):
    import uvicorn
    from server import create_app
    uvicorn.run(create_app(watch_dirs=args.dirs), host=args.host, port=args.port)


def cmd_mcp(args):
    from mcp_server import OpenClawMCPServer, create_http_app
    server = OpenClawMCPServer()
    if args.http:
        import uvicorn
        uvicorn.run(create_http_app(server), host=args.host, port=args.port)
    else:
        server.run_stdio()


def cmd_agents(args):
    hub = RuntimeAgentHub()
    if args.agent_action == "list":
        if args.filter == "local":
            agents = hub.get_local_agents()
        elif args.filter == "verified":
            agents = hub.get_verified_agents()
        elif args.filter == "free":
            agents = hub.get_free_agents()
        else:
            agents = [agent.to_dict() for agent in hub.agents.values()]
        emit({"count": len(agents), "agents": agents})
    elif args.agent_action == "test":
        results = hub.test_all()
        hub.save_state()
        emit({"results": results, "report": hub.get_report()})
    elif args.agent_action == "query":
        emit(hub.query(args.agent, args.prompt))
    elif args.agent_action == "route":
        emit(hub.route_query(args.prompt, prefer_local=not args.allow_cloud_first))
    elif args.agent_action == "report":
        emit(hub.get_report())


def cmd_mesh(args):
    from src.mesh_intelligence import MeshIntelligence

    if args.mesh_action == "cloud":
        from src.cloud_storage import create_cloud_manager
        manager = create_cloud_manager()
        if args.cloud_action in {"add", "configure"}:
            target = {}
            if args.repo:
                target["repo"] = args.repo
            if args.path:
                target["path"] = args.path
            ok = manager.configure_provider(
                args.provider,
                credential_env=args.credential_env,
                target=target,
            )
            emit({"status": "configured" if ok else "rejected", "provider": args.provider, "credential_env": args.credential_env, "target": target})
        elif args.cloud_action == "connect":
            emit(manager.connect_all())
        elif args.cloud_action == "status":
            emit(manager.get_status())
        elif args.cloud_action == "sync":
            mesh = MeshIntelligence(args.node_id or "kcbflux-mesh")
            emit(manager.sync_knowledge(mesh.knowledge))
        return

    mesh = MeshIntelligence(args.node_id or "kcbflux-mesh")
    if args.mesh_action == "start":
        mesh.start()
        if args.port:
            mesh.node.port = args.port
        emit(mesh.get_status())
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            mesh.stop()
    elif args.mesh_action == "status":
        emit(mesh.get_status())
    elif args.mesh_action == "store":
        value = json.loads(args.value) if args.value else {}
        mesh.store_knowledge(args.key, value, args.tags.split(",") if args.tags else [])
        emit({"status": "stored", "key": args.key})
    elif args.mesh_action == "get":
        value = mesh.get_knowledge(args.key)
        emit({"key": args.key, "found": value is not None, "value": value})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openclaw", description="Controlled automation runtime and integrity watchdog")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Create integrity baseline")
    scan.add_argument("--dirs", nargs="+", default=["."])
    scan.set_defaults(func=cmd_scan)

    check = sub.add_parser("check", help="Check integrity against baseline")
    check.add_argument("--dirs", nargs="+", default=["."])
    check.set_defaults(func=cmd_check)

    daemon = sub.add_parser("daemon", help="Run integrity monitor")
    daemon.add_argument("--dirs", nargs="+", default=["."])
    daemon.add_argument("--interval", type=float, default=2.0)
    daemon.set_defaults(func=cmd_daemon)

    action = sub.add_parser("action", help="Run a governed action")
    action.add_argument("--type", required=True)
    action.add_argument("--target", default="")
    action.add_argument("--params-json")
    action.add_argument("--x", type=int)
    action.add_argument("--y", type=int)
    action.add_argument("--principal", default="cli-operator")
    action.add_argument("--idempotency-key")
    action.add_argument("--human-approved", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    action.set_defaults(func=cmd_action)

    audit = sub.add_parser("audit", help="Read or verify action ledger")
    audit.add_argument("--limit", type=int)
    audit.add_argument("--verify", action="store_true")
    audit.set_defaults(func=cmd_audit)

    report = sub.add_parser("report", help="Integrity report")
    report.add_argument("--dirs", nargs="+", default=["."])
    report.set_defaults(func=cmd_report)

    doctor = sub.add_parser("doctor", help="Runtime health")
    doctor.set_defaults(func=cmd_doctor)

    serve = sub.add_parser("serve", help="Run REST API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8088)
    serve.add_argument("--dirs", nargs="+", default=["."])
    serve.set_defaults(func=cmd_serve)

    mcp = sub.add_parser("mcp", help="Run MCP server")
    mcp.add_argument("--http", action="store_true")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=8089)
    mcp.set_defaults(func=cmd_mcp)

    agents = sub.add_parser("agents", help="Agent hub")
    agent_sub = agents.add_subparsers(dest="agent_action", required=True)
    agent_list = agent_sub.add_parser("list")
    agent_list.add_argument("--filter", choices=["all", "local", "verified", "free"], default="all")
    agent_list.set_defaults(func=cmd_agents)
    agent_test = agent_sub.add_parser("test")
    agent_test.set_defaults(func=cmd_agents)
    agent_query = agent_sub.add_parser("query")
    agent_query.add_argument("--agent", required=True)
    agent_query.add_argument("--prompt", required=True)
    agent_query.set_defaults(func=cmd_agents)
    agent_route = agent_sub.add_parser("route")
    agent_route.add_argument("--prompt", required=True)
    agent_route.add_argument("--allow-cloud-first", action="store_true")
    agent_route.set_defaults(func=cmd_agents)
    agent_report = agent_sub.add_parser("report")
    agent_report.set_defaults(func=cmd_agents)

    mesh = sub.add_parser("mesh", help="Mesh intelligence")
    mesh_sub = mesh.add_subparsers(dest="mesh_action", required=True)
    mesh_start = mesh_sub.add_parser("start")
    mesh_start.add_argument("--node-id")
    mesh_start.add_argument("--port", type=int, default=8090)
    mesh_start.set_defaults(func=cmd_mesh)
    mesh_status = mesh_sub.add_parser("status")
    mesh_status.add_argument("--node-id")
    mesh_status.set_defaults(func=cmd_mesh)
    mesh_store = mesh_sub.add_parser("store")
    mesh_store.add_argument("--node-id")
    mesh_store.add_argument("--key", required=True)
    mesh_store.add_argument("--value")
    mesh_store.add_argument("--tags")
    mesh_store.set_defaults(func=cmd_mesh)
    mesh_get = mesh_sub.add_parser("get")
    mesh_get.add_argument("--node-id")
    mesh_get.add_argument("--key", required=True)
    mesh_get.set_defaults(func=cmd_mesh)

    cloud = mesh_sub.add_parser("cloud")
    cloud_sub = cloud.add_subparsers(dest="cloud_action", required=True)
    for command_name in ("add", "configure"):
        configure = cloud_sub.add_parser(command_name)
        configure.add_argument("--provider", choices=["dropbox", "github"], required=True)
        configure.add_argument("--credential-env", required=True)
        configure.add_argument("--repo")
        configure.add_argument("--path")
        configure.set_defaults(func=cmd_mesh)
    cloud_connect = cloud_sub.add_parser("connect")
    cloud_connect.set_defaults(func=cmd_mesh)
    cloud_status = cloud_sub.add_parser("status")
    cloud_status.set_defaults(func=cmd_mesh)
    cloud_sync = cloud_sub.add_parser("sync")
    cloud_sync.add_argument("--node-id")
    cloud_sync.set_defaults(func=cmd_mesh)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
