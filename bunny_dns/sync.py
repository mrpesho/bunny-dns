"""
Main orchestrator for syncing bunny.net configuration.
"""

import json
from pathlib import Path
from typing import Any, Optional, Union

from .bunny_client import BunnyClient
from .dns_manager import DNSManager
from .pullzone_manager import PullZoneManager
from .edge_rules_manager import EdgeRulesManager


class BunnySync:
    """Orchestrates syncing DNS zones, Pull Zones, and Edge Rules."""

    def __init__(self, api_key: str):
        self.client = BunnyClient(api_key)
        self.dns_manager = DNSManager(self.client)
        self.pullzone_manager = PullZoneManager(self.client)
        self.edge_rules_manager = EdgeRulesManager(self.client)

    def load_config(self, config: Union[dict, str, Path]) -> dict:
        """
        Load configuration from dict, JSON string, or file path.

        Args:
            config: Configuration as dict, JSON string, or path to JSON file

        Returns:
            Parsed configuration dict
        """
        if isinstance(config, dict):
            return config
        elif isinstance(config, Path) or (isinstance(config, str) and Path(config).exists()):
            path = Path(config)
            with open(path) as f:
                return json.load(f)
        elif isinstance(config, str):
            return json.loads(config)
        else:
            raise ValueError(f"Invalid config type: {type(config)}")

    def _filter_domains(self, domains_config: dict, domain_filter: Optional[str]) -> dict:
        """Filter domains config by domain name if filter is specified."""
        if domain_filter is None:
            return domains_config
        # Match exact domain or allow wildcard matching
        filtered = {}
        for domain, config in domains_config.items():
            if domain.lower() == domain_filter.lower():
                filtered[domain] = config
        return filtered

    def sync(
        self,
        config: Union[dict, str, Path],
        dry_run: bool = False,
        delete_extra_records: bool = True,
        domain: Optional[str] = None,
    ) -> dict:
        """
        Sync all resources to match configuration.

        Args:
            config: Configuration dict, JSON string, or path to JSON file
            dry_run: If True, only report changes without making them
            delete_extra_records: If True, delete DNS records not in config
            domain: If specified, only sync this domain (and its pull zones)

        Returns:
            Dict with all sync results
        """
        config_data = self.load_config(config)
        results = {
            "dry_run": dry_run,
            "domain_filter": domain,
            "dns_zones": [],
            "pull_zones": [],
            "summary": {
                "dns_records_created": 0,
                "dns_records_updated": 0,
                "dns_records_deleted": 0,
                "pull_zones_created": 0,
                "pull_zones_updated": 0,
                "hostnames_added": 0,
                "hostnames_removed": 0,
                "edge_rules_created": 0,
                "edge_rules_deleted": 0,
            },
        }

        # Get domains config and apply filter
        domains_config = config_data.get("domains", {})
        domains_config = self._filter_domains(domains_config, domain)

        if domain and not domains_config:
            raise ValueError(f"Domain '{domain}' not found in configuration")

        # Process each domain
        for domain_name, domain_config in domains_config.items():
            # Sync DNS records for this domain
            dns_records = domain_config.get("dns_records", [])
            if dns_records:
                result = self.dns_manager.sync_zone(
                    domain=domain_name,
                    desired_records=dns_records,
                    dry_run=dry_run,
                    delete_extra=delete_extra_records,
                )
                results["dns_zones"].append(result)
                results["summary"]["dns_records_created"] += len(result.get("created", []))
                results["summary"]["dns_records_updated"] += len(result.get("updated", []))
                results["summary"]["dns_records_deleted"] += len(result.get("deleted", []))

            # Sync Pull Zones for this domain
            pull_zones_config = domain_config.get("pull_zones", {})
            for pz_name, pz_config in pull_zones_config.items():
                # Sync the pull zone itself
                pz_result = self.pullzone_manager.sync_zone(
                    name=pz_name,
                    config=pz_config,
                    dry_run=dry_run,
                )
                pz_result["domain"] = domain_name
                results["pull_zones"].append(pz_result)

                if pz_result.get("created"):
                    results["summary"]["pull_zones_created"] += 1
                if pz_result.get("updated"):
                    results["summary"]["pull_zones_updated"] += 1
                results["summary"]["hostnames_added"] += len(pz_result.get("hostnames_added", []))
                results["summary"]["hostnames_removed"] += len(pz_result.get("hostnames_removed", []))

                # Sync edge rules for this pull zone
                edge_rules_config = pz_config.get("edge_rules", [])
                if edge_rules_config:
                    # Get the pull zone ID
                    zone = self.pullzone_manager.get_zone_by_name(pz_name)
                    if zone:
                        er_result = self.edge_rules_manager.sync_rules(
                            zone_id=zone.id,
                            rule_configs=edge_rules_config,
                            dry_run=dry_run,
                        )
                        pz_result["edge_rules"] = er_result
                        results["summary"]["edge_rules_created"] += len(er_result.get("created", []))
                        results["summary"]["edge_rules_deleted"] += len(er_result.get("deleted", []))

        return results

    def sync_dns_only(
        self,
        config: Union[dict, str, Path],
        dry_run: bool = False,
        delete_extra_records: bool = True,
        domain: Optional[str] = None,
    ) -> dict:
        """Sync only DNS zones."""
        config_data = self.load_config(config)
        results = {"dry_run": dry_run, "domain_filter": domain, "dns_zones": []}

        domains_config = config_data.get("domains", {})
        domains_config = self._filter_domains(domains_config, domain)

        if domain and not domains_config:
            raise ValueError(f"Domain '{domain}' not found in configuration")

        for domain_name, domain_config in domains_config.items():
            dns_records = domain_config.get("dns_records", [])
            if dns_records:
                result = self.dns_manager.sync_zone(
                    domain=domain_name,
                    desired_records=dns_records,
                    dry_run=dry_run,
                    delete_extra=delete_extra_records,
                )
                results["dns_zones"].append(result)

        return results

    def sync_pullzones_only(
        self,
        config: Union[dict, str, Path],
        dry_run: bool = False,
        domain: Optional[str] = None,
    ) -> dict:
        """Sync only Pull Zones (without edge rules)."""
        config_data = self.load_config(config)
        results = {"dry_run": dry_run, "domain_filter": domain, "pull_zones": []}

        domains_config = config_data.get("domains", {})
        domains_config = self._filter_domains(domains_config, domain)

        if domain and not domains_config:
            raise ValueError(f"Domain '{domain}' not found in configuration")

        for domain_name, domain_config in domains_config.items():
            pull_zones_config = domain_config.get("pull_zones", {})
            for pz_name, pz_config in pull_zones_config.items():
                result = self.pullzone_manager.sync_zone(
                    name=pz_name,
                    config=pz_config,
                    dry_run=dry_run,
                )
                result["domain"] = domain_name
                results["pull_zones"].append(result)

        return results


def print_results(results: dict) -> None:
    """Print sync results in a human-readable format."""
    if results.get("dry_run"):
        print("=== DRY RUN MODE (no changes made) ===\n")
    if results.get("domain_filter"):
        print(f"=== Syncing domain: {results['domain_filter']} ===\n")

    # DNS Zones
    if results.get("dns_zones"):
        print("DNS ZONES:")
        print("-" * 40)
        for zone in results["dns_zones"]:
            print(f"\n  {zone['zone']}:")
            if zone.get("zone_created"):
                print("    [NEW ZONE CREATED]")
            if zone.get("created"):
                print(f"    Created: {len(zone['created'])} records")
                for rec in zone["created"]:
                    print(f"      + {rec}")
            if zone.get("updated"):
                print(f"    Updated: {len(zone['updated'])} records")
                for rec in zone["updated"]:
                    print(f"      ~ {rec}")
            if zone.get("deleted"):
                print(f"    Deleted: {len(zone['deleted'])} records")
                for rec in zone["deleted"]:
                    print(f"      - {rec}")
            if zone.get("unchanged"):
                print(f"    Unchanged: {len(zone['unchanged'])} records")

    # Pull Zones
    if results.get("pull_zones"):
        print("\nPULL ZONES:")
        print("-" * 40)
        for zone in results["pull_zones"]:
            print(f"\n  {zone['zone']}:")
            if zone.get("created"):
                print("    [NEW ZONE CREATED]")
            if zone.get("updated"):
                print("    [ZONE UPDATED]")
            for change in zone.get("changes", []):
                print(f"    {change}")
            if zone.get("edge_rules"):
                er = zone["edge_rules"]
                if er.get("deleted"):
                    print(f"    Edge rules deleted: {len(er['deleted'])}")
                if er.get("created"):
                    print(f"    Edge rules created: {len(er['created'])}")
                    for rule in er["created"]:
                        print(f"      + {rule}")

    # Summary
    if results.get("summary"):
        s = results["summary"]
        print("\nSUMMARY:")
        print("-" * 40)
        print(f"  DNS records: {s['dns_records_created']} created, "
              f"{s['dns_records_updated']} updated, "
              f"{s['dns_records_deleted']} deleted")
        print(f"  Pull zones: {s['pull_zones_created']} created, "
              f"{s['pull_zones_updated']} updated")
        print(f"  Hostnames: {s['hostnames_added']} added, "
              f"{s['hostnames_removed']} removed")
        print(f"  Edge rules: {s['edge_rules_created']} created, "
              f"{s['edge_rules_deleted']} deleted")
