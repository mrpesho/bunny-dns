#!/usr/bin/env python3
"""
CLI entry point for bunny.net DNS and Pull Zone auto-setup.

Usage:
    python main.py --config config.json --domain example.com
    python main.py --config config.json --domain example.com --dry-run
    python main.py --config config.json --domain example.com --dns-only
    python main.py --config config.json  # syncs all domains in config
    python main.py --sot bunny --domain example.com  # pull from bunny.net
    python main.py --sot bunny --all  # pull all zones from bunny.net
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from .sync import BunnySync, print_results


def main():
    parser = argparse.ArgumentParser(
        description="Sync DNS zones and Pull Zones on bunny.net from configuration"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to JSON configuration file (required for --sot local)",
    )
    parser.add_argument(
        "--domain", "-d",
        help="Only sync this specific domain (recommended to avoid affecting other domains)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be changed without making any changes",
    )
    parser.add_argument(
        "--dns-only",
        action="store_true",
        help="Only sync DNS zones",
    )
    parser.add_argument(
        "--pullzones-only",
        action="store_true",
        help="Only sync Pull Zones (without edge rules)",
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Don't delete DNS records not in config (additive mode)",
    )
    parser.add_argument(
        "--api-key",
        help="bunny.net API key (defaults to BUNNY_API_KEY env var)",
    )
    parser.add_argument(
        "--sot",
        choices=["local", "bunny"],
        default="local",
        help="Source of truth: 'local' pushes config to bunny.net (default), 'bunny' pulls current state",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="pull_all",
        help="With --sot bunny: pull all DNS zones on the account",
    )
    parser.add_argument(
        "--output", "-o",
        help="With --sot bunny: write output to file instead of stdout",
    )

    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or os.environ.get("BUNNY_API_KEY")
    if not api_key:
        print("Error: API key required. Set BUNNY_API_KEY env var or use --api-key", file=sys.stderr)
        sys.exit(1)

    if args.sot == "bunny":
        # Pull mode
        if not args.domain and not args.pull_all:
            print("Error: --sot bunny requires either --domain or --all", file=sys.stderr)
            sys.exit(1)

        try:
            syncer = BunnySync(api_key)
            config = syncer.pull(
                domain=args.domain,
                pull_all=args.pull_all,
                dns_only=args.dns_only,
                pullzones_only=args.pullzones_only,
            )
            if config is None:
                print(
                    f"Error: Domain '{args.domain}' not found on your account. "
                    f"Check if you typed the domain correctly.",
                    file=sys.stderr,
                )
                sys.exit(1)
            output = json.dumps(config, indent=2)
            if args.output:
                with open(args.output, "w") as f:
                    f.write(output + "\n")
                print(f"Config written to {args.output}", file=sys.stderr)
            else:
                print(output)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Push mode (existing behavior)
        if not args.config:
            print("Error: --config is required for --sot local", file=sys.stderr)
            sys.exit(1)

        if not os.path.exists(args.config):
            print(f"Error: Config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)

        try:
            syncer = BunnySync(api_key)

            if args.dns_only:
                results = syncer.sync_dns_only(
                    config=args.config,
                    dry_run=args.dry_run,
                    delete_extra_records=not args.no_delete,
                    domain=args.domain,
                )
            elif args.pullzones_only:
                results = syncer.sync_pullzones_only(
                    config=args.config,
                    dry_run=args.dry_run,
                    domain=args.domain,
                )
            else:
                results = syncer.sync(
                    config=args.config,
                    dry_run=args.dry_run,
                    delete_extra_records=not args.no_delete,
                    domain=args.domain,
                )

            print_results(results)

            # Exit with error if nothing was synced (possible config issue)
            if not results.get("dns_zones") and not results.get("pull_zones"):
                print("\nWarning: No resources found in config to sync.", file=sys.stderr)

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
