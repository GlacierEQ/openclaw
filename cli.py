#!/usr/bin/env python3
"""OpenClaw CLI — Command-line interface for file integrity, action governance, and AI agents."""

import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / ".integrity"))

# Load env
env_file = Path.home() / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

from watchdog_daemon import WatchdogDaemon
from src.openclaw import OpenClawEngine
from src.agent_hub import FreeTierAgentHub


def cmd_scan(args):
    daemon = WatchdogDaemon(watch_dirs=args.dirs)
    result = daemon.initial_scan()
    print(json.dumps(result, indent=2))


def cmd_check(args):
    daemon = WatchdogDaemon(watch_dirs=args.dirs)
    result = daemon.check_integrity()
    print(json.dumps(result, indent=2))


def cmd_daemon(args):
    daemon = WatchdogDaemon(watch_dirs=args.dirs, poll_interval=args.interval)
    daemon.initial_scan()
    daemon.run_daemon()


def cmd_action(args):
    engine = OpenClawEngine()
    result = engine.execute_action(
        action_type=args.type,
        target=args.target,
        coords=(args.x, args.y) if args.x is not None else None,
    )
    print(json.dumps(result, indent=2))


def cmd_audit(args):
    engine = OpenClawEngine()
    history = engine.get_audit_trail()
    if args.limit:
        history = history[-args.limit:]
    print(json.dumps(history, indent=2))


def cmd_report(args):
    daemon = WatchdogDaemon(watch_dirs=args.dirs)
    print(json.dumps(daemon.get_report(), indent=2))


# === Agent Commands ===

def cmd_agents_list(args):
    hub = FreeTierAgentHub()
    if args.filter == "local":
        agents = hub.get_local_agents()
    elif args.filter == "verified":
        agents = hub.get_verified_agents()
    elif args.filter == "free":
        agents = hub.get_free_agents()
    else:
        agents = [a.to_dict() for a in hub.agents.values()]

    print(f"Available agents: {len(agents)}")
    print()
    for a in agents:
        tier_icon = "🏠" if a["tier"] == "local" else "☁️"
        status_icon = "✅" if a["status"] == "verified" else "❌" if a["status"] == "failed" else "⏳"
        print(f"  {status_icon} {tier_icon} {a['name']:35} | {a['provider']:12} | {a['model']}")


def cmd_agents_test(args):
    hub = FreeTierAgentHub()
    print("Testing agents...")
    print()

    results = hub.test_all()
    for name, result in results.items():
        status = result.get("status", "?")
        agent = hub.agents[name]
        tier_icon = "🏠" if agent.tier.value == "local" else "☁️"
        if status == "verified":
            latency = result.get("latency_ms", 0)
            print(f"  ✅ {tier_icon} {name:30} | {latency:7.0f}ms")
        else:
            error = result.get("error", "?")[:40]
            print(f"  ❌ {tier_icon} {name:30} | {error}")

    hub.save_state()
    print()
    report = hub.get_report()
    print(f"Verified: {report['verified']}/{report['total_agents']} (Local: {report['local_verified']})")


def cmd_agents_query(args):
    hub = FreeTierAgentHub()
    result = hub.query(args.agent, args.prompt)
    if "response" in result:
        print(f"Agent: {result['agent']}")
        print(f"Latency: {result.get('latency_ms', 0):.0f}ms")
        print()
        print(result["response"])
    else:
        print(f"Error: {result.get('error')}")


def cmd_agents_route(args):
    hub = FreeTierAgentHub()
    result = hub.route_query(args.prompt)
    if "response" in result:
        print(f"Routed to: {result['agent']}")
        print(f"Latency: {result.get('latency_ms', 0):.0f}ms")
        print()
        print(result["response"])
    else:
        print(f"Error: {result.get('error')}")


def cmd_agents_report(args):
    hub = FreeTierAgentHub()
    report = hub.get_report()
    print(json.dumps(report, indent=2))


def cmd_mesh(args):
    """Mesh intelligence commands."""
    from src.mesh_intelligence import MeshIntelligence
    
    if args.mesh_action == "start":
        node_id = args.node_id or "kcbflux-mesh"
        mesh = MeshIntelligence(node_id)
        mesh.start()
        
        if args.port:
            mesh.node.port = args.port
        
        print(f"[Mesh] Node {mesh.node_id} started")
        print(f"[Mesh] IP: {mesh.node.ip_address}:{mesh.node.port}")
        print(f"[Mesh] Role: {mesh.node.role}")
        print(f"[Mesh] Capabilities: {mesh.node.capability.specialties}")
        print()
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            mesh.stop()
    
    elif args.mesh_action == "status":
        node_id = args.node_id or "kcbflux-mesh"
        mesh = MeshIntelligence(node_id)
        print(json.dumps(mesh.get_status(), indent=2))
    
    elif args.mesh_action == "store":
        mesh = MeshIntelligence(args.node_id or "kcbflux-mesh")
        key = args.key
        value = json.loads(args.value) if args.value else {}
        tags = args.tags.split(",") if args.tags else []
        
        mesh.store_knowledge(key, value, tags)
        print(f"[Mesh] Stored: {key}")
        print(f"[Mesh] Value: {value}")
    
    elif args.mesh_action == "get":
        mesh = MeshIntelligence(args.node_id or "kcbflux-mesh")
        value = mesh.get_knowledge(args.key)
        
        if value:
            print(f"[Mesh] {args.key}: {json.dumps(value, indent=2)}")
        else:
            print(f"[Mesh] Key not found: {args.key}")
    
    elif args.mesh_action == "cloud":
        from src.cloud_storage import create_cloud_manager, StorageProvider
        
        manager = create_cloud_manager()
        
        if args.cloud_action == "add":
            if args.provider == "dropbox":
                manager.add_provider(StorageProvider.DROPBOX, {"access_token": args.token})
                print("[Mesh] Dropbox added")
            elif args.provider == "github":
                manager.add_provider(StorageProvider.GITHUB, {"token": args.token})
                print("[Mesh] GitHub added")
        
        elif args.cloud_action == "connect":
            results = manager.connect_all()
            for provider, success in results.items():
                print(f"[Mesh] {provider.value}: {'✅' if success else '❌'}")
        
        elif args.cloud_action == "status":
            print(json.dumps(manager.get_status(), indent=2))
        
        elif args.cloud_action == "sync":
            mesh = MeshIntelligence(args.node_id or "kcbflux-mesh")
            results = manager.sync_knowledge(mesh.knowledge)
            for provider, success in results.items():
                print(f"[Mesh] {provider.value}: {'✅' if success else '❌'}")
    
    else:
        print("[Mesh] Unknown mesh action")


def main():
    parser = argparse.ArgumentParser(
        prog="openclaw",
        description="OpenClaw — File Integrity, Action Governor & AI Agent Hub",
    )
    subparsers = parser.add_subparsers(dest="command")

    # scan
    p_scan = subparsers.add_parser("scan", help="Initial directory scan")
    p_scan.add_argument("--dirs", nargs="+", default=["."])
    p_scan.set_defaults(func=cmd_scan)

    # check
    p_check = subparsers.add_parser("check", help="Integrity check")
    p_check.add_argument("--dirs", nargs="+", default=["."])
    p_check.set_defaults(func=cmd_check)

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="Run watchdog daemon")
    p_daemon.add_argument("--dirs", nargs="+", default=["."])
    p_daemon.add_argument("--interval", type=float, default=2.0)
    p_daemon.set_defaults(func=cmd_daemon)

    # action
    p_action = subparsers.add_parser("action", help="Execute governed action")
    p_action.add_argument("--type", required=True, help="Action type")
    p_action.add_argument("--target", required=True, help="Target element")
    p_action.add_argument("--x", type=int, help="X coordinate")
    p_action.add_argument("--y", type=int, help="Y coordinate")
    p_action.set_defaults(func=cmd_action)

    # audit
    p_audit = subparsers.add_parser("audit", help="View audit trail")
    p_audit.add_argument("--limit", type=int, help="Limit entries")
    p_audit.set_defaults(func=cmd_audit)

    # report
    p_report = subparsers.add_parser("report", help="Integrity report")
    p_report.add_argument("--dirs", nargs="+", default=["."])
    p_report.set_defaults(func=cmd_report)

    # === Agent Subcommands ===
    p_agents = subparsers.add_parser("agents", help="AI Agent Hub")

    agents_sub = p_agents.add_subparsers(dest="agent_command")

    # agents list
    p_agents_list = agents_sub.add_parser("list", help="List available agents")
    p_agents_list.add_argument("--filter", choices=["all", "local", "verified", "free"], default="all")
    p_agents_list.set_defaults(func=cmd_agents_list)

    # agents test
    p_agents_test = agents_sub.add_parser("test", help="Test all agents")
    p_agents_test.set_defaults(func=cmd_agents_test)

    # agents query
    p_agents_query = agents_sub.add_parser("query", help="Query specific agent")
    p_agents_query.add_argument("--agent", required=True, help="Agent name")
    p_agents_query.add_argument("--prompt", required=True, help="Your prompt")
    p_agents_query.set_defaults(func=cmd_agents_query)

    # agents route
    p_agents_route = agents_sub.add_parser("route", help="Auto-route to best agent")
    p_agents_route.add_argument("--prompt", required=True, help="Your prompt")
    p_agents_route.set_defaults(func=cmd_agents_route)

    # agents report
    p_agents_report = agents_sub.add_parser("report", help="Agent status report")
    p_agents_report.set_defaults(func=cmd_agents_report)

    # === Mesh Subcommands ===
    p_mesh = subparsers.add_parser("mesh", help="Mesh Intelligence")
    
    mesh_sub = p_mesh.add_subparsers(dest="mesh_action")
    
    # mesh start
    p_mesh_start = mesh_sub.add_parser("start", help="Start mesh node")
    p_mesh_start.add_argument("--node-id", help="Node ID")
    p_mesh_start.add_argument("--port", type=int, default=8090)
    p_mesh_start.set_defaults(func=cmd_mesh)
    
    # mesh status
    p_mesh_status = mesh_sub.add_parser("status", help="Mesh status")
    p_mesh_status.add_argument("--node-id", help="Node ID")
    p_mesh_status.set_defaults(func=cmd_mesh)
    
    # mesh store
    p_mesh_store = mesh_sub.add_parser("store", help="Store knowledge")
    p_mesh_store.add_argument("--key", required=True, help="Knowledge key")
    p_mesh_store.add_argument("--value", help="JSON value")
    p_mesh_store.add_argument("--tags", help="Comma-separated tags")
    p_mesh_store.add_argument("--node-id", help="Node ID")
    p_mesh_store.set_defaults(func=cmd_mesh)
    
    # mesh get
    p_mesh_get = mesh_sub.add_parser("get", help="Get knowledge")
    p_mesh_get.add_argument("--key", required=True, help="Knowledge key")
    p_mesh_get.add_argument("--node-id", help="Node ID")
    p_mesh_get.set_defaults(func=cmd_mesh)
    
    # mesh cloud
    p_mesh_cloud = mesh_sub.add_parser("cloud", help="Cloud storage")
    cloud_sub = p_mesh_cloud.add_subparsers(dest="cloud_action")
    
    # mesh cloud add
    p_cloud_add = cloud_sub.add_parser("add", help="Add cloud provider")
    p_cloud_add.add_argument("--provider", required=True, choices=["dropbox", "github", "google"])
    p_cloud_add.add_argument("--token", required=True)
    p_cloud_add.add_argument("--node-id", help="Node ID")
    p_cloud_add.set_defaults(func=cmd_mesh)
    
    # mesh cloud connect
    p_cloud_connect = cloud_sub.add_parser("connect", help="Connect all providers")
    p_cloud_connect.set_defaults(func=cmd_mesh)
    
    # mesh cloud status
    p_cloud_status = cloud_sub.add_parser("status", help="Cloud status")
    p_cloud_status.set_defaults(func=cmd_mesh)
    
    # mesh cloud sync
    p_cloud_sync = cloud_sub.add_parser("sync", help="Sync to cloud")
    p_cloud_sync.add_argument("--node-id", help="Node ID")
    p_cloud_sync.set_defaults(func=cmd_mesh)

    args = parser.parse_args()
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
