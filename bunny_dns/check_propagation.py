#!/usr/bin/env python3
"""
Check DNS propagation status for domains configured with bunny.net.

Usage:
    python check_propagation.py example.com
    python check_propagation.py example.com --config config.json
"""

import argparse
import json
import ssl
import subprocess
import sys
from urllib.request import Request, urlopen


BUNNY_NAMESERVERS = {"kiki.bunny.net", "coco.bunny.net"}


def run_dig(query_type: str, domain: str) -> list[str]:
    """Run dig command and return results."""
    try:
        result = subprocess.run(
            ["dig", query_type, domain, "+short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        return [line.strip().rstrip(".") for line in lines if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def check_https(hostname: str) -> dict:
    """Check if HTTPS is working for a hostname."""
    try:
        ctx = ssl.create_default_context()
        req = Request(
            f"https://{hostname}",
            method="HEAD",
            headers={"User-Agent": "bunny-dns/1.0"}
        )
        with urlopen(req, timeout=10, context=ctx) as response:
            return {"status": "ok", "code": response.status}
    except ssl.SSLError as e:
        return {"status": "ssl_error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_domain(domain: str, config: dict = None) -> dict:
    """Check propagation status for a domain."""
    results = {
        "domain": domain,
        "nameservers": {"status": "unknown", "current": []},
        "records": [],
        "hostnames": [],
    }

    # Check nameservers
    ns_records = run_dig("NS", domain)
    ns_lower = {ns.lower() for ns in ns_records}
    results["nameservers"]["current"] = ns_records

    if ns_lower == BUNNY_NAMESERVERS:
        results["nameservers"]["status"] = "ok"
    elif ns_lower & BUNNY_NAMESERVERS:
        results["nameservers"]["status"] = "partial"
    else:
        results["nameservers"]["status"] = "not_bunny"

    # Check some basic records
    for record_type in ["A", "AAAA", "MX"]:
        values = run_dig(record_type, domain)
        if values:
            results["records"].append({
                "type": record_type,
                "name": "@",
                "values": values,
                "status": "resolving"
            })

    # Check www
    www_values = run_dig("CNAME", f"www.{domain}")
    if not www_values:
        www_values = run_dig("A", f"www.{domain}")
    if www_values:
        results["records"].append({
            "type": "CNAME/A",
            "name": "www",
            "values": www_values,
            "status": "resolving"
        })

    # If config provided, check pull zone hostnames
    if config:
        domain_config = config.get("domains", {}).get(domain, {})
        for zone_name, zone_config in domain_config.get("pull_zones", {}).items():
            for hostname in zone_config.get("hostnames", []):
                cname_values = run_dig("CNAME", hostname)
                https_result = check_https(hostname)

                results["hostnames"].append({
                    "hostname": hostname,
                    "zone": zone_name,
                    "cname": cname_values[0] if cname_values else None,
                    "ssl": https_result["status"],
                    "ssl_detail": https_result.get("error") or https_result.get("code"),
                })

    return results


def print_results(results: dict):
    """Print results in a readable format."""
    domain = results["domain"]
    print(f"\n{'='*60}")
    print(f" DNS Propagation Check: {domain}")
    print(f"{'='*60}\n")

    # Nameservers
    ns = results["nameservers"]
    status_icon = {"ok": "✓", "partial": "~", "not_bunny": "✗", "unknown": "?"}
    icon = status_icon.get(ns["status"], "?")

    print(f"NAMESERVERS: {icon} {ns['status'].upper()}")
    print(f"  Expected: {', '.join(sorted(BUNNY_NAMESERVERS))}")
    print(f"  Current:  {', '.join(ns['current']) or '(none found)'}")

    if ns["status"] == "ok":
        print("  → DNS is pointing to bunny.net")
    elif ns["status"] == "not_bunny":
        print("  → Update nameservers at your registrar")
    print()

    # Records
    if results["records"]:
        print("DNS RECORDS:")
        for rec in results["records"]:
            values_str = ", ".join(rec["values"][:3])
            if len(rec["values"]) > 3:
                values_str += f" (+{len(rec['values'])-3} more)"
            print(f"  ✓ {rec['type']:8} {rec['name']:20} → {values_str}")
        print()

    # Hostnames (SSL)
    if results["hostnames"]:
        print("PULL ZONE HOSTNAMES:")
        for h in results["hostnames"]:
            ssl_icon = "✓" if h["ssl"] == "ok" else "✗"
            cname_str = h["cname"] or "(not resolving)"
            print(f"  {ssl_icon} {h['hostname']}")
            print(f"      CNAME: {cname_str}")
            print(f"      SSL:   {h['ssl']} {f'({h["ssl_detail"]})' if h['ssl_detail'] else ''}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Check DNS propagation status for bunny.net domains"
    )
    parser.add_argument("domain", help="Domain to check")
    parser.add_argument(
        "-c", "--config",
        help="Path to config.json (to check pull zone hostnames)",
    )

    args = parser.parse_args()

    config = None
    if args.config:
        try:
            with open(args.config) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load config: {e}", file=sys.stderr)

    results = check_domain(args.domain, config)
    print_results(results)


if __name__ == "__main__":
    main()
