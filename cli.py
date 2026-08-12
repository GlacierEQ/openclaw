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

    args = parser.parse_args()
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
