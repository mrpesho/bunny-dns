"""
Tests for pullzone_manager.py - Pull Zone management.
"""

from unittest.mock import Mock, MagicMock

import pytest

from bunny_dns.pullzone_manager import (
    PULLZONE_TYPES,
    Hostname,
    PullZone,
    PullZoneManager,
)


class TestPullZoneTypes:
    """Test pull zone type mappings."""

    def test_standard_type(self):
        assert PULLZONE_TYPES["standard"] == 0

    def test_volume_type(self):
        assert PULLZONE_TYPES["volume"] == 1


class TestHostname:
    """Test Hostname dataclass."""

    def test_default_values(self):
        hostname = Hostname(value="cdn.example.com")
        assert hostname.id is None
        assert hostname.force_ssl is True
        assert hostname.has_certificate is False
        assert hostname.is_system_hostname is False

    def test_from_api_response(self):
        data = {
            "Id": 123,
            "Value": "cdn.example.com",
            "ForceSSL": True,
            "HasCertificate": True,
            "IsSystemHostname": False,
        }
        hostname = Hostname.from_api_response(data)

        assert hostname.id == 123
        assert hostname.value == "cdn.example.com"
        assert hostname.force_ssl is True
        assert hostname.has_certificate is True
        assert hostname.is_system_hostname is False

    def test_from_api_response_system_hostname(self):
        data = {
            "Id": 1,
            "Value": "my-cdn.b-cdn.net",
            "ForceSSL": True,
            "HasCertificate": True,
            "IsSystemHostname": True,
        }
        hostname = Hostname.from_api_response(data)

        assert hostname.is_system_hostname is True


class TestPullZone:
    """Test PullZone dataclass."""

    def test_default_values(self):
        zone = PullZone(name="my-cdn")
        assert zone.id is None
        assert zone.origin_url is None
        assert zone.type == 0
        assert zone.enabled is True
        assert zone.hostnames == []
        assert zone.enable_geo_zone_us is True
        assert zone.enable_geo_zone_eu is True
        assert zone.enable_geo_zone_asia is True
        assert zone.enable_geo_zone_sa is True
        assert zone.enable_geo_zone_af is True

    def test_from_api_response(self, sample_pullzone_response):
        zone = PullZone.from_api_response(sample_pullzone_response)

        assert zone.id == 67890
        assert zone.name == "my-cdn"
        assert zone.origin_url == "https://origin.example.com"
        assert zone.origin_host_header == "origin.example.com"
        assert zone.type == 0
        assert zone.enabled is True
        assert len(zone.hostnames) == 2
        assert zone.enable_geo_zone_us is True
        assert zone.enable_geo_zone_eu is True
        assert zone.enable_geo_zone_asia is True
        assert zone.enable_geo_zone_sa is False
        assert zone.enable_geo_zone_af is False

    def test_to_api_payload_basic(self):
        zone = PullZone(name="my-cdn")
        payload = zone.to_api_payload()

        assert payload["Name"] == "my-cdn"
        assert payload["Type"] == 0
        assert "OriginUrl" not in payload  # None values excluded
        assert payload["EnableGeoZoneUS"] is True
        assert payload["EnableGeoZoneEU"] is True

    def test_to_api_payload_with_origin(self):
        zone = PullZone(
            name="my-cdn",
            origin_url="https://origin.example.com",
            origin_host_header="origin.example.com",
        )
        payload = zone.to_api_payload()

        assert payload["OriginUrl"] == "https://origin.example.com"
        assert payload["OriginHostHeader"] == "origin.example.com"

    def test_to_api_payload_volume_type(self):
        zone = PullZone(name="my-cdn", type=1)
        payload = zone.to_api_payload()

        assert payload["Type"] == 1

    def test_to_api_payload_region_flags(self):
        zone = PullZone(
            name="my-cdn",
            enable_geo_zone_us=True,
            enable_geo_zone_eu=True,
            enable_geo_zone_asia=False,
            enable_geo_zone_sa=False,
            enable_geo_zone_af=False,
        )
        payload = zone.to_api_payload()

        assert payload["EnableGeoZoneUS"] is True
        assert payload["EnableGeoZoneEU"] is True
        assert payload["EnableGeoZoneASIA"] is False
        assert payload["EnableGeoZoneSA"] is False
        assert payload["EnableGeoZoneAF"] is False


class TestPullZoneManager:
    """Test PullZoneManager API interactions."""

    @pytest.fixture
    def pz_manager(self, mock_client):
        return PullZoneManager(mock_client)

    def test_list_zones(self, pz_manager):
        pz_manager.client.get = Mock(return_value=[
            {"Id": 1, "Name": "zone1", "Hostnames": []},
            {"Id": 2, "Name": "zone2", "Hostnames": []},
        ])

        zones = pz_manager.list_zones()

        pz_manager.client.get.assert_called_once_with("/pullzone")
        assert len(zones) == 2
        assert zones[0].name == "zone1"

    def test_list_zones_handles_non_list(self, pz_manager):
        pz_manager.client.get = Mock(return_value=None)
        zones = pz_manager.list_zones()
        assert zones == []

    def test_get_zone(self, pz_manager, sample_pullzone_response):
        pz_manager.client.get = Mock(return_value=sample_pullzone_response)

        zone = pz_manager.get_zone(67890)

        pz_manager.client.get.assert_called_once_with("/pullzone/67890")
        assert zone.name == "my-cdn"

    def test_get_zone_by_name_found(self, pz_manager):
        pz_manager.client.get = Mock(return_value=[
            {"Id": 1, "Name": "my-cdn", "Hostnames": []},
        ])

        zone = pz_manager.get_zone_by_name("my-cdn")

        assert zone is not None
        assert zone.name == "my-cdn"

    def test_get_zone_by_name_case_insensitive(self, pz_manager):
        pz_manager.client.get = Mock(return_value=[
            {"Id": 1, "Name": "My-CDN", "Hostnames": []},
        ])

        zone = pz_manager.get_zone_by_name("my-cdn")

        assert zone is not None

    def test_get_zone_by_name_not_found(self, pz_manager):
        pz_manager.client.get = Mock(return_value=[])

        zone = pz_manager.get_zone_by_name("not-found")

        assert zone is None

    def test_create_zone(self, pz_manager, sample_pullzone_response):
        pz_manager.client.post = Mock(return_value=sample_pullzone_response)

        zone = PullZone(name="my-cdn", origin_url="https://origin.example.com")
        result = pz_manager.create_zone(zone)

        pz_manager.client.post.assert_called_once()
        call_args = pz_manager.client.post.call_args
        assert call_args[0][0] == "/pullzone"
        assert result.id == 67890

    def test_update_zone(self, pz_manager, sample_pullzone_response):
        pz_manager.client.post = Mock(return_value=sample_pullzone_response)

        zone = PullZone(name="my-cdn", origin_url="https://new-origin.example.com")
        result = pz_manager.update_zone(67890, zone)

        pz_manager.client.post.assert_called_once()
        call_args = pz_manager.client.post.call_args
        assert call_args[0][0] == "/pullzone/67890"

    def test_delete_zone(self, pz_manager):
        pz_manager.client.delete = Mock(return_value=None)

        pz_manager.delete_zone(67890)

        pz_manager.client.delete.assert_called_once_with("/pullzone/67890")

    def test_add_hostname(self, pz_manager):
        pz_manager.client.post = Mock(return_value=None)

        pz_manager.add_hostname(67890, "cdn.example.com")

        pz_manager.client.post.assert_called_once_with(
            "/pullzone/67890/addHostname",
            {"Hostname": "cdn.example.com"},
        )

    def test_remove_hostname(self, pz_manager):
        pz_manager.client.delete = Mock(return_value=None)

        pz_manager.remove_hostname(67890, "cdn.example.com")

        pz_manager.client.delete.assert_called_once_with(
            "/pullzone/67890/removeHostname",
            params={"hostname": "cdn.example.com"},
        )

    def test_load_free_certificate(self, pz_manager):
        pz_manager.client.get = Mock(return_value=None)

        pz_manager.load_free_certificate("cdn.example.com")

        pz_manager.client.get.assert_called_once_with(
            "/pullzone/loadFreeCertificate",
            params={"hostname": "cdn.example.com"},
        )

    def test_set_force_ssl(self, pz_manager):
        pz_manager.client.post = Mock(return_value=None)

        pz_manager.set_force_ssl(67890, "cdn.example.com", force=True)

        pz_manager.client.post.assert_called_once_with(
            "/pullzone/67890/setForceSSL",
            {"Hostname": "cdn.example.com", "ForceSSL": True},
        )


class TestPullZoneManagerSyncZone:
    """Test sync_zone orchestration logic."""

    @pytest.fixture
    def pz_manager(self, mock_client):
        manager = PullZoneManager(mock_client)
        # Ensure client methods don't interfere
        manager.client.post = Mock(return_value=None)
        manager.client.delete = Mock(return_value=None)
        manager.client.get = Mock(return_value=None)
        return manager

    def test_sync_creates_new_zone(self, pz_manager, sample_pullzone_response):
        pz_manager.get_zone_by_name = Mock(return_value=None)
        created_zone = PullZone.from_api_response(sample_pullzone_response)
        created_zone.hostnames = []  # New zone has no custom hostnames
        pz_manager.create_zone = Mock(return_value=created_zone)
        pz_manager.add_hostname = Mock()
        pz_manager.load_free_certificate = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "origin_url": "https://origin.example.com",
                "hostnames": ["cdn.example.com"],
            },
        )

        assert result["created"] is True
        pz_manager.create_zone.assert_called_once()

    def test_sync_updates_origin_url(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        existing_zone.origin_url = "https://old-origin.example.com"
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.update_zone = Mock(return_value=existing_zone)
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "origin_url": "https://new-origin.example.com",
            },
        )

        assert result["updated"] is True
        assert any("origin URL" in c for c in result["changes"])

    def test_sync_updates_origin_host_header(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        existing_zone.origin_host_header = "old.example.com"
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.update_zone = Mock(return_value=existing_zone)
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "origin_host_header": "new.example.com",
            },
        )

        assert result["updated"] is True

    def test_sync_updates_zone_type(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        existing_zone.type = 0  # standard
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.update_zone = Mock(return_value=existing_zone)
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={"type": "volume"},
        )

        assert result["updated"] is True
        assert any("zone type" in c for c in result["changes"])

    def test_sync_updates_regions(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        # Zone has US, EU, ASIA enabled; SA, AF disabled
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.update_zone = Mock(return_value=existing_zone)
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={"enabled_regions": ["EU", "US"]},  # Disable ASIA
        )

        assert result["updated"] is True
        assert any("regions" in c.lower() for c in result["changes"])

    def test_sync_adds_hostname(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        # Has cdn.example.com, adding new.example.com
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.add_hostname = Mock()
        pz_manager.load_free_certificate = Mock()
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "hostnames": ["cdn.example.com", "new.example.com"],
                # Match fixture's region settings to avoid update
                "enabled_regions": ["EU", "US", "ASIA"],
            },
        )

        assert "new.example.com" in result["hostnames_added"]
        pz_manager.add_hostname.assert_called_once_with(67890, "new.example.com")
        pz_manager.load_free_certificate.assert_called_once()

    def test_sync_removes_hostname(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        # Has cdn.example.com, removing it
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "hostnames": [],  # Remove all custom hostnames
                "enabled_regions": ["EU", "US", "ASIA"],  # Match fixture
            },
        )

        assert "cdn.example.com" in result["hostnames_removed"]
        pz_manager.remove_hostname.assert_called_once()

    def test_sync_ignores_system_hostname(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        # System hostname my-cdn.b-cdn.net should not be removed
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "hostnames": [],
                "enabled_regions": ["EU", "US", "ASIA"],  # Match fixture
            },
        )

        # Only cdn.example.com should be removed, not the system hostname
        assert len(result["hostnames_removed"]) == 1
        assert "b-cdn.net" not in result["hostnames_removed"][0]

    def test_sync_hostname_case_insensitive(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        # Has cdn.example.com (lowercase)
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.add_hostname = Mock()
        pz_manager.remove_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "hostnames": ["CDN.EXAMPLE.COM"],  # Different case
                "enabled_regions": ["EU", "US", "ASIA"],  # Match fixture
            },
        )

        # Should recognize as same hostname, not add duplicate
        assert len(result["hostnames_added"]) == 0

    def test_sync_dry_run_no_changes(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.add_hostname = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={"hostnames": ["new.example.com"]},
            dry_run=True,
        )

        assert "new.example.com" in result["hostnames_added"]
        pz_manager.add_hostname.assert_not_called()

    def test_sync_dry_run_new_zone(self, pz_manager):
        pz_manager.get_zone_by_name = Mock(return_value=None)
        pz_manager.create_zone = Mock()

        result = pz_manager.sync_zone(
            name="new-cdn",
            config={
                "origin_url": "https://origin.example.com",
                "hostnames": ["cdn.example.com"],
            },
            dry_run=True,
        )

        assert result["created"] is True
        assert "cdn.example.com" in result["hostnames_added"]
        pz_manager.create_zone.assert_not_called()

    def test_sync_default_regions(self, pz_manager, sample_pullzone_response):
        created_zone = PullZone.from_api_response(sample_pullzone_response)
        created_zone.hostnames = []
        pz_manager.get_zone_by_name = Mock(return_value=None)
        pz_manager.create_zone = Mock(return_value=created_zone)

        pz_manager.sync_zone(
            name="my-cdn",
            config={"origin_url": "https://origin.example.com"},
            # No enabled_regions specified - should default to all
        )

        call_args = pz_manager.create_zone.call_args[0][0]
        assert call_args.enable_geo_zone_us is True
        assert call_args.enable_geo_zone_eu is True
        assert call_args.enable_geo_zone_asia is True
        assert call_args.enable_geo_zone_sa is True
        assert call_args.enable_geo_zone_af is True

    def test_sync_certificate_error_continues(self, pz_manager, sample_pullzone_response):
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        existing_zone.hostnames = [h for h in existing_zone.hostnames if h.is_system_hostname]
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.add_hostname = Mock()
        pz_manager.load_free_certificate = Mock(side_effect=Exception("Certificate failed"))

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "hostnames": ["new.example.com"],
                "enabled_regions": ["EU", "US", "ASIA"],  # Match fixture
            },
        )

        # Hostname was added despite certificate error
        assert "new.example.com" in result["hostnames_added"]
        # Error was logged in changes
        assert any("Warning" in c for c in result["changes"])

    def test_sync_retries_certificate_for_existing_hostname(self, pz_manager, sample_pullzone_response):
        """Test that sync retries loading certificate for existing hostnames without one."""
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        # Mark cdn.example.com as not having a certificate
        for h in existing_zone.hostnames:
            if h.value == "cdn.example.com":
                h.has_certificate = False
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.load_free_certificate = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "hostnames": ["cdn.example.com"],
                "enabled_regions": ["EU", "US", "ASIA"],
            },
        )

        # Should attempt to load certificate for existing hostname
        pz_manager.load_free_certificate.assert_called_once_with("cdn.example.com")
        assert "cdn.example.com" in result["certificates_loaded"]
        assert any("Loading certificate" in c for c in result["changes"])

    def test_sync_skips_certificate_if_already_present(self, pz_manager, sample_pullzone_response):
        """Test that sync doesn't retry certificate for hostnames that already have one."""
        existing_zone = PullZone.from_api_response(sample_pullzone_response)
        # cdn.example.com already has certificate in fixture
        pz_manager.get_zone_by_name = Mock(return_value=existing_zone)
        pz_manager.load_free_certificate = Mock()

        result = pz_manager.sync_zone(
            name="my-cdn",
            config={
                "hostnames": ["cdn.example.com"],
                "enabled_regions": ["EU", "US", "ASIA"],
            },
        )

        # Should not attempt to load certificate
        pz_manager.load_free_certificate.assert_not_called()
        assert len(result["certificates_loaded"]) == 0
