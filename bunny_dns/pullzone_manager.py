"""
Pull Zone management for bunny.net.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from .bunny_client import BunnyClient, BunnyNotFoundError


# Pull Zone type mapping
PULLZONE_TYPES = {
    "standard": 0,
    "volume": 1,
}


@dataclass
class Hostname:
    """Represents a custom hostname on a Pull Zone."""
    value: str
    id: Optional[int] = None
    force_ssl: bool = True
    has_certificate: bool = False
    is_system_hostname: bool = False

    @classmethod
    def from_api_response(cls, data: dict) -> "Hostname":
        return cls(
            id=data.get("Id"),
            value=data.get("Value", ""),
            force_ssl=data.get("ForceSSL", False),
            has_certificate=data.get("HasCertificate", False),
            is_system_hostname=data.get("IsSystemHostname", False),
        )


@dataclass
class PullZone:
    """Represents a Pull Zone."""
    name: str
    id: Optional[int] = None
    origin_url: Optional[str] = None
    origin_host_header: Optional[str] = None
    type: int = 0
    enabled: bool = True
    hostnames: list[Hostname] = field(default_factory=list)
    edge_rules: list[dict] = field(default_factory=list)

    # Pricing zones (regions)
    enable_geo_zone_us: bool = True
    enable_geo_zone_eu: bool = True
    enable_geo_zone_asia: bool = True
    enable_geo_zone_sa: bool = True
    enable_geo_zone_af: bool = True

    @classmethod
    def from_api_response(cls, data: dict) -> "PullZone":
        hostnames = [
            Hostname.from_api_response(h)
            for h in data.get("Hostnames", [])
        ]
        return cls(
            id=data.get("Id"),
            name=data.get("Name", ""),
            origin_url=data.get("OriginUrl"),
            origin_host_header=data.get("OriginHostHeader"),
            type=data.get("Type", 0),
            enabled=data.get("Enabled", True),
            hostnames=hostnames,
            edge_rules=data.get("EdgeRules", []),
            enable_geo_zone_us=data.get("EnableGeoZoneUS", True),
            enable_geo_zone_eu=data.get("EnableGeoZoneEU", True),
            enable_geo_zone_asia=data.get("EnableGeoZoneASIA", True),
            enable_geo_zone_sa=data.get("EnableGeoZoneSA", True),
            enable_geo_zone_af=data.get("EnableGeoZoneAF", True),
        )

    def to_api_payload(self) -> dict:
        """Convert to API request payload for create/update."""
        payload = {
            "Name": self.name,
            "Type": self.type,
            "EnableGeoZoneUS": self.enable_geo_zone_us,
            "EnableGeoZoneEU": self.enable_geo_zone_eu,
            "EnableGeoZoneASIA": self.enable_geo_zone_asia,
            "EnableGeoZoneSA": self.enable_geo_zone_sa,
            "EnableGeoZoneAF": self.enable_geo_zone_af,
        }
        if self.origin_url:
            payload["OriginUrl"] = self.origin_url
        if self.origin_host_header:
            payload["OriginHostHeader"] = self.origin_host_header
        return payload


class PullZoneManager:
    """Manages Pull Zones on bunny.net."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def list_zones(self) -> list[PullZone]:
        """List all Pull Zones."""
        response = self.client.get("/pullzone")
        items = response if isinstance(response, list) else []
        return [PullZone.from_api_response(z) for z in items]

    def get_zone(self, zone_id: int) -> PullZone:
        """Get a Pull Zone by ID."""
        response = self.client.get(f"/pullzone/{zone_id}")
        return PullZone.from_api_response(response)

    def get_zone_by_name(self, name: str) -> Optional[PullZone]:
        """Find a Pull Zone by name."""
        zones = self.list_zones()
        for zone in zones:
            if zone.name.lower() == name.lower():
                return zone
        return None

    def create_zone(self, zone: PullZone) -> PullZone:
        """Create a new Pull Zone."""
        payload = zone.to_api_payload()
        response = self.client.post("/pullzone", payload)
        return PullZone.from_api_response(response)

    def update_zone(self, zone_id: int, zone: PullZone) -> PullZone:
        """Update an existing Pull Zone."""
        payload = zone.to_api_payload()
        response = self.client.post(f"/pullzone/{zone_id}", payload)
        return PullZone.from_api_response(response)

    def delete_zone(self, zone_id: int) -> None:
        """Delete a Pull Zone."""
        self.client.delete(f"/pullzone/{zone_id}")

    def add_hostname(self, zone_id: int, hostname: str) -> None:
        """Add a custom hostname to a Pull Zone."""
        self.client.post(f"/pullzone/{zone_id}/addHostname", {"Hostname": hostname})

    def remove_hostname(self, zone_id: int, hostname: str) -> None:
        """Remove a custom hostname from a Pull Zone."""
        self.client.delete(f"/pullzone/{zone_id}/removeHostname", params={"hostname": hostname})

    def load_free_certificate(self, hostname: str) -> None:
        """Load a free SSL certificate for a hostname."""
        self.client.get("/pullzone/loadFreeCertificate", params={"hostname": hostname})

    def set_force_ssl(self, zone_id: int, hostname: str, force: bool = True) -> None:
        """Enable or disable Force SSL for a hostname."""
        self.client.post(f"/pullzone/{zone_id}/setForceSSL", {
            "Hostname": hostname,
            "ForceSSL": force,
        })

    def sync_zone(
        self,
        name: str,
        config: dict,
        dry_run: bool = False,
    ) -> dict:
        """
        Sync a Pull Zone to match desired configuration.

        Args:
            name: Pull Zone name
            config: Configuration dict with origin_url, hostnames, etc.
            dry_run: If True, only report changes without making them

        Returns:
            Dict with changes made
        """
        result = {
            "zone": name,
            "created": False,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "certificates_loaded": [],
            "changes": [],
        }

        # Parse config
        origin_url = config.get("origin_url")
        origin_host_header = config.get("origin_host_header")
        zone_type = PULLZONE_TYPES.get(config.get("type", "standard"), 0)
        desired_hostnames = set(config.get("hostnames", []))
        force_ssl = config.get("force_ssl", None)

        # Parse enabled regions
        regions = config.get("enabled_regions", ["EU", "US", "ASIA", "SA", "AF"])
        regions_upper = [r.upper() for r in regions]

        # Get or create zone
        zone = self.get_zone_by_name(name)
        if zone is None:
            result["created"] = True
            result["changes"].append(f"Creating pull zone '{name}'")
            if not dry_run:
                new_zone = PullZone(
                    name=name,
                    origin_url=origin_url,
                    origin_host_header=origin_host_header,
                    type=zone_type,
                    enable_geo_zone_us="US" in regions_upper,
                    enable_geo_zone_eu="EU" in regions_upper,
                    enable_geo_zone_asia="ASIA" in regions_upper,
                    enable_geo_zone_sa="SA" in regions_upper,
                    enable_geo_zone_af="AF" in regions_upper,
                )
                zone = self.create_zone(new_zone)
        else:
            # Check if update needed
            needs_update = False
            if origin_url and zone.origin_url != origin_url:
                needs_update = True
                result["changes"].append(f"Updating origin URL: {zone.origin_url} -> {origin_url}")
            if origin_host_header and zone.origin_host_header != origin_host_header:
                needs_update = True
                result["changes"].append(f"Updating origin host header: {zone.origin_host_header} -> {origin_host_header}")
            if zone.type != zone_type:
                needs_update = True
                result["changes"].append(f"Updating zone type: {zone.type} -> {zone_type}")

            # Check region changes
            region_changes = []
            if zone.enable_geo_zone_us != ("US" in regions_upper):
                region_changes.append(f"US: {zone.enable_geo_zone_us} -> {'US' in regions_upper}")
            if zone.enable_geo_zone_eu != ("EU" in regions_upper):
                region_changes.append(f"EU: {zone.enable_geo_zone_eu} -> {'EU' in regions_upper}")
            if zone.enable_geo_zone_asia != ("ASIA" in regions_upper):
                region_changes.append(f"ASIA: {zone.enable_geo_zone_asia} -> {'ASIA' in regions_upper}")
            if zone.enable_geo_zone_sa != ("SA" in regions_upper):
                region_changes.append(f"SA: {zone.enable_geo_zone_sa} -> {'SA' in regions_upper}")
            if zone.enable_geo_zone_af != ("AF" in regions_upper):
                region_changes.append(f"AF: {zone.enable_geo_zone_af} -> {'AF' in regions_upper}")

            if region_changes:
                needs_update = True
                result["changes"].append(f"Updating regions: {', '.join(region_changes)}")

            if needs_update:
                result["updated"] = True
                if not dry_run:
                    updated_zone = PullZone(
                        name=name,
                        origin_url=origin_url,
                        origin_host_header=origin_host_header,
                        type=zone_type,
                        enable_geo_zone_us="US" in regions_upper,
                        enable_geo_zone_eu="EU" in regions_upper,
                        enable_geo_zone_asia="ASIA" in regions_upper,
                        enable_geo_zone_sa="SA" in regions_upper,
                        enable_geo_zone_af="AF" in regions_upper,
                    )
                    zone = self.update_zone(zone.id, updated_zone)

        # Sync hostnames
        # In dry-run mode for new zones, zone is None - skip hostname sync but report planned additions
        if zone is None:
            for hostname in desired_hostnames:
                result["hostnames_added"].append(hostname)
                result["changes"].append(f"Adding hostname: {hostname}")
            return result

        current_hostnames = {
            h.value.lower(): h
            for h in zone.hostnames
            if not h.is_system_hostname
        }
        desired_hostnames_lower = {h.lower() for h in desired_hostnames}

        # Add missing hostnames
        for hostname in desired_hostnames:
            if hostname.lower() not in current_hostnames:
                result["hostnames_added"].append(hostname)
                result["changes"].append(f"Adding hostname: {hostname}")
                if not dry_run:
                    self.add_hostname(zone.id, hostname)
                    # Load free certificate
                    try:
                        self.load_free_certificate(hostname)
                        result["certificates_loaded"].append(hostname)
                    except Exception as e:
                        result["changes"].append(f"Warning: Could not load certificate for {hostname}: {e}")
                    # Set Force SSL if configured
                    if force_ssl is not None:
                        try:
                            self.set_force_ssl(zone.id, hostname, force=force_ssl)
                            state = "Enabled" if force_ssl else "Disabled"
                            result["changes"].append(f"{state} Force SSL for {hostname}")
                        except Exception as e:
                            result["changes"].append(f"Warning: Could not set Force SSL for {hostname}: {e}")

        # Retry loading certificates for existing hostnames that don't have one
        for hostname in desired_hostnames:
            hostname_lower = hostname.lower()
            if hostname_lower in current_hostnames:
                hostname_obj = current_hostnames[hostname_lower]
                if not hostname_obj.has_certificate:
                    result["changes"].append(f"Loading certificate for {hostname}")
                    if not dry_run:
                        try:
                            self.load_free_certificate(hostname)
                            result["certificates_loaded"].append(hostname)
                        except Exception as e:
                            result["changes"].append(f"Warning: Could not load certificate for {hostname}: {e}")

        # Set Force SSL for existing hostnames where state doesn't match
        if force_ssl is not None:
            for hostname in desired_hostnames:
                hostname_lower = hostname.lower()
                if hostname_lower in current_hostnames:
                    hostname_obj = current_hostnames[hostname_lower]
                    if hostname_obj.force_ssl != force_ssl:
                        state = "Enabling" if force_ssl else "Disabling"
                        result["changes"].append(f"{state} Force SSL for {hostname}")
                        if not dry_run:
                            try:
                                self.set_force_ssl(zone.id, hostname, force=force_ssl)
                            except Exception as e:
                                result["changes"].append(f"Warning: Could not set Force SSL for {hostname}: {e}")

        # Remove extra hostnames
        for hostname_lower, hostname_obj in current_hostnames.items():
            if hostname_lower not in desired_hostnames_lower:
                result["hostnames_removed"].append(hostname_obj.value)
                result["changes"].append(f"Removing hostname: {hostname_obj.value}")
                if not dry_run:
                    self.remove_hostname(zone.id, hostname_obj.value)

        return result
