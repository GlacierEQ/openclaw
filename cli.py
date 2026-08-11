#!/usr/bin/env python3
"""OpenClaw CLI — Command-line interface for file integrity and action governance."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / ".integrity"))
from watchdog_daemon import WatchdogDaemon
from src.openclaw import OpenClawEngine


def cmd_scan(args):
    daemon = WatchdogDaemon(watch_dirs=args.dirs)
    result = daemon.initial_scan()
    print(json.dumps(result, indent=2))


def cmd_check(args):
    daemon = WatchdogDaemon(watch_dirs=args.dirs)
    result = daemon.check_integrity()
    print(json.dumps(result, indent=2))


def cmd_daemon(args):
    daemon = WatchdogDaemon(
        watch_dirs=args.dirs,
        poll_interval=args.interval,
    )
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


def main():
    parser = argparse.ArgumentParser(
        prog="openclaw",
        description="OpenClaw — File Integrity Watchdog & Action Governor",
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

    args = parser.parse_args()
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
