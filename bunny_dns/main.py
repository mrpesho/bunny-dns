#!/usr/bin/env python3
"""
CLI entry point for bunny.net DNS and Pull Zone auto-setup.

Usage:
    python main.py --config config.json --domain example.com
    python main.py --config config.json --domain example.com --dry-run
    python main.py --config config.json --domain example.com --dns-only
    python main.py --config config.json  # syncs all domains in config
"""

import argparse
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
        required=True,
        help="Path to JSON configuration file",
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

    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or os.environ.get("BUNNY_API_KEY")
    if not api_key:
        print("Error: API key required. Set BUNNY_API_KEY env var or use --api-key", file=sys.stderr)
        sys.exit(1)

    # Validate config file exists
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
