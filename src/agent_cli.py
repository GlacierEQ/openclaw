"""Command-line interface for the OpenClaw free-agent fabric."""
from __future__ import annotations

import argparse
import json

from .agent_runtime import RuntimeAgentHub


def emit(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(prog="openclaw-agents", description="Discover and run OpenClaw free/local model endpoints")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover")

    listing = sub.add_parser("list")
    listing.add_argument("--filter", choices=["all", "free", "local", "verified"], default="all")

    test = sub.add_parser("test")
    test.add_argument("--agent")

    query = sub.add_parser("query")
    query.add_argument("--agent", required=True)
    query.add_argument("--prompt", required=True)
    query.add_argument("--mode", choices=["code", "plan", "debug", "review"], default="code")

    route = sub.add_parser("route")
    route.add_argument("--prompt", required=True)
    route.add_argument("--mode", choices=["code", "plan", "debug", "review"], default="code")
    route.add_argument("--cloud-first", action="store_true")

    fanout = sub.add_parser("fanout")
    fanout.add_argument("--prompt", required=True)
    fanout.add_argument("--mode", choices=["plan", "review", "debug", "code"], default="plan")
    fanout.add_argument("--max-agents", type=int, default=0, help="0 means all discovered free endpoints")

    sub.add_parser("report")
    args = parser.parse_args()
    hub = RuntimeAgentHub()

    if args.command == "discover":
        agents = hub.discover()
        emit({"count": len(agents), "report": hub.get_report(), "agents": agents})
    elif args.command == "list":
        if args.filter == "free":
            agents = hub.get_free_agents()
        elif args.filter == "local":
            agents = hub.get_local_agents()
        elif args.filter == "verified":
            agents = hub.get_verified_agents()
        else:
            agents = [agent.to_dict() for agent in hub.agents.values()]
        emit({"count": len(agents), "agents": agents})
    elif args.command == "test":
        emit(hub.test_agent(args.agent) if args.agent else hub.test_all())
    elif args.command == "query":
        emit(hub.query(args.agent, args.prompt, mode=args.mode))
    elif args.command == "route":
        emit(hub.route_query(args.prompt, prefer_local=not args.cloud_first, mode=args.mode))
    elif args.command == "fanout":
        emit(hub.fanout(args.prompt, max_agents=args.max_agents, mode=args.mode))
    elif args.command == "report":
        emit(hub.get_report())


if __name__ == "__main__":
    main()
