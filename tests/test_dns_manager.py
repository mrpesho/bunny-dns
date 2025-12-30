"""
Tests for dns_manager.py - DNS zone and record management.
"""

from unittest.mock import Mock, MagicMock, patch

import pytest

from dns_manager import (
    DNS_RECORD_TYPES,
    DNS_RECORD_TYPES_REVERSE,
    DNSRecord,
    DNSZone,
    DNSManager,
)


class TestDNSRecordTypes:
    """Test DNS record type mappings."""

    def test_all_types_defined(self):
        expected_types = ["A", "AAAA", "CNAME", "TXT", "MX", "RDR", "PZ", "SRV", "CAA", "PTR", "SCR", "NS"]
        for t in expected_types:
            assert t in DNS_RECORD_TYPES

    def test_type_values(self):
        assert DNS_RECORD_TYPES["A"] == 0
        assert DNS_RECORD_TYPES["AAAA"] == 1
        assert DNS_RECORD_TYPES["CNAME"] == 2
        assert DNS_RECORD_TYPES["TXT"] == 3
        assert DNS_RECORD_TYPES["MX"] == 4
        assert DNS_RECORD_TYPES["SRV"] == 8
        assert DNS_RECORD_TYPES["NS"] == 12

    def test_reverse_mapping(self):
        for name, value in DNS_RECORD_TYPES.items():
            assert DNS_RECORD_TYPES_REVERSE[value] == name


class TestDNSRecord:
    """Test DNSRecord dataclass."""

    def test_default_values(self):
        record = DNSRecord(type="A", name="test", value="1.2.3.4")
        assert record.ttl == 300
        assert record.priority is None
        assert record.weight is None
        assert record.port is None
        assert record.id is None

    def test_to_api_payload_basic(self):
        record = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=600)
        payload = record.to_api_payload()

        assert payload["Type"] == 0
        assert payload["Name"] == "www"
        assert payload["Value"] == "1.2.3.4"
        assert payload["Ttl"] == 600
        assert "Priority" not in payload

    def test_to_api_payload_with_priority(self):
        record = DNSRecord(type="MX", name="@", value="mail.example.com", priority=10)
        payload = record.to_api_payload()

        assert payload["Type"] == 4
        assert payload["Priority"] == 10

    def test_to_api_payload_srv_record(self):
        record = DNSRecord(
            type="SRV",
            name="_sip._tcp",
            value="sip.example.com",
            priority=10,
            weight=5,
            port=5060,
        )
        payload = record.to_api_payload()

        assert payload["Type"] == 8
        assert payload["Priority"] == 10
        assert payload["Weight"] == 5
        assert payload["Port"] == 5060

    def test_from_api_response(self):
        data = {
            "Id": 123,
            "Type": 2,
            "Name": "www",
            "Value": "example.com",
            "Ttl": 300,
            "Priority": 0,
            "Weight": 0,
            "Port": 0,
        }
        record = DNSRecord.from_api_response(data)

        assert record.id == 123
        assert record.type == "CNAME"
        assert record.name == "www"
        assert record.value == "example.com"
        assert record.ttl == 300

    def test_from_api_response_unknown_type(self):
        data = {"Type": 999, "Name": "test", "Value": "test"}
        record = DNSRecord.from_api_response(data)
        assert record.type == "A"  # Default fallback


class TestDNSRecordNormalization:
    """Test name normalization - critical for @ vs empty string comparison."""

    def test_normalize_at_symbol(self):
        record = DNSRecord(type="A", name="@", value="1.2.3.4")
        assert record._normalize_name("@") == ""

    def test_normalize_empty_string(self):
        record = DNSRecord(type="A", name="", value="1.2.3.4")
        assert record._normalize_name("") == ""

    def test_normalize_preserves_subdomain(self):
        record = DNSRecord(type="A", name="www", value="1.2.3.4")
        assert record._normalize_name("www") == "www"

    def test_normalize_lowercase(self):
        record = DNSRecord(type="A", name="WWW", value="1.2.3.4")
        assert record._normalize_name("WWW") == "www"

    def test_normalize_strips_whitespace(self):
        record = DNSRecord(type="A", name=" www ", value="1.2.3.4")
        assert record._normalize_name(" www ") == "www"

    def test_normalize_optional_none(self):
        record = DNSRecord(type="A", name="@", value="1.2.3.4")
        assert record._normalize_optional(None) == 0

    def test_normalize_optional_zero(self):
        record = DNSRecord(type="A", name="@", value="1.2.3.4")
        assert record._normalize_optional(0) == 0

    def test_normalize_optional_value(self):
        record = DNSRecord(type="A", name="@", value="1.2.3.4")
        assert record._normalize_optional(10) == 10


class TestDNSRecordMatching:
    """Test record matching logic."""

    def test_matches_identical_records(self):
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4")
        r2 = DNSRecord(type="A", name="www", value="1.2.3.4")
        assert r1.matches(r2)

    def test_matches_different_case_type(self):
        r1 = DNSRecord(type="a", name="www", value="1.2.3.4")
        r2 = DNSRecord(type="A", name="www", value="1.2.3.4")
        assert r1.matches(r2)

    def test_matches_at_vs_empty(self):
        """Critical test: config uses @ but API returns empty string."""
        r1 = DNSRecord(type="A", name="@", value="1.2.3.4")
        r2 = DNSRecord(type="A", name="", value="1.2.3.4")
        assert r1.matches(r2)

    def test_matches_different_case_name(self):
        r1 = DNSRecord(type="A", name="WWW", value="1.2.3.4")
        r2 = DNSRecord(type="A", name="www", value="1.2.3.4")
        assert r1.matches(r2)

    def test_no_match_different_type(self):
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4")
        r2 = DNSRecord(type="AAAA", name="www", value="1.2.3.4")
        assert not r1.matches(r2)

    def test_no_match_different_name(self):
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4")
        r2 = DNSRecord(type="A", name="api", value="1.2.3.4")
        assert not r1.matches(r2)

    def test_no_match_different_value(self):
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4")
        r2 = DNSRecord(type="A", name="www", value="5.6.7.8")
        assert not r1.matches(r2)


class TestDNSRecordNeedsUpdate:
    """Test update detection logic."""

    def test_no_update_identical(self):
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=300)
        r2 = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=300)
        assert not r1.needs_update(r2)

    def test_needs_update_ttl_changed(self):
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=300)
        r2 = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=600)
        assert r1.needs_update(r2)

    def test_needs_update_priority_changed(self):
        r1 = DNSRecord(type="MX", name="@", value="mail.example.com", priority=10)
        r2 = DNSRecord(type="MX", name="@", value="mail.example.com", priority=20)
        assert r1.needs_update(r2)

    def test_no_update_priority_none_vs_zero(self):
        """Config has None, API returns 0 - should not trigger update."""
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4", priority=None)
        r2 = DNSRecord(type="A", name="www", value="1.2.3.4", priority=0)
        assert not r1.needs_update(r2)

    def test_no_update_weight_none_vs_zero(self):
        r1 = DNSRecord(type="SRV", name="_sip", value="sip.com", weight=None)
        r2 = DNSRecord(type="SRV", name="_sip", value="sip.com", weight=0)
        assert not r1.needs_update(r2)

    def test_no_update_non_matching_records(self):
        r1 = DNSRecord(type="A", name="www", value="1.2.3.4")
        r2 = DNSRecord(type="A", name="api", value="1.2.3.4")
        # Non-matching records always return False
        assert not r1.needs_update(r2)


class TestDNSZone:
    """Test DNSZone dataclass."""

    def test_default_values(self):
        zone = DNSZone(domain="example.com")
        assert zone.id is None
        assert zone.records == []

    def test_from_api_response(self, sample_dns_zone_response):
        zone = DNSZone.from_api_response(sample_dns_zone_response)

        assert zone.id == 12345
        assert zone.domain == "example.com"
        assert len(zone.records) == 3
        assert zone.records[0].type == "A"
        assert zone.records[1].type == "CNAME"
        assert zone.records[2].type == "MX"


class TestDNSManager:
    """Test DNSManager API interactions."""

    @pytest.fixture
    def dns_manager(self, mock_client):
        return DNSManager(mock_client)

    def test_list_zones(self, dns_manager, mock_response):
        dns_manager.client.get = Mock(return_value={
            "Items": [
                {"Id": 1, "Domain": "example.com", "Records": []},
                {"Id": 2, "Domain": "test.com", "Records": []},
            ]
        })

        zones = dns_manager.list_zones()

        dns_manager.client.get.assert_called_once_with("/dnszone")
        assert len(zones) == 2
        assert zones[0].domain == "example.com"
        assert zones[1].domain == "test.com"

    def test_list_zones_empty(self, dns_manager):
        dns_manager.client.get = Mock(return_value=None)
        zones = dns_manager.list_zones()
        assert zones == []

    def test_get_zone(self, dns_manager, sample_dns_zone_response):
        dns_manager.client.get = Mock(return_value=sample_dns_zone_response)

        zone = dns_manager.get_zone(12345)

        dns_manager.client.get.assert_called_once_with("/dnszone/12345")
        assert zone.id == 12345
        assert zone.domain == "example.com"

    def test_get_zone_by_domain_found(self, dns_manager, sample_dns_zone_response):
        dns_manager.client.get = Mock(side_effect=[
            {"Items": [{"Id": 12345, "Domain": "example.com", "Records": []}]},
            sample_dns_zone_response,
        ])

        zone = dns_manager.get_zone_by_domain("example.com")

        assert zone is not None
        assert zone.domain == "example.com"

    def test_get_zone_by_domain_case_insensitive(self, dns_manager, sample_dns_zone_response):
        dns_manager.client.get = Mock(side_effect=[
            {"Items": [{"Id": 12345, "Domain": "Example.COM", "Records": []}]},
            sample_dns_zone_response,
        ])

        zone = dns_manager.get_zone_by_domain("example.com")

        assert zone is not None

    def test_get_zone_by_domain_not_found(self, dns_manager):
        dns_manager.client.get = Mock(return_value={"Items": []})

        zone = dns_manager.get_zone_by_domain("notfound.com")

        assert zone is None

    def test_create_zone(self, dns_manager, sample_dns_zone_response):
        dns_manager.client.post = Mock(return_value=sample_dns_zone_response)

        zone = dns_manager.create_zone("example.com")

        dns_manager.client.post.assert_called_once_with("/dnszone", {"Domain": "example.com"})
        assert zone.domain == "example.com"

    def test_delete_zone(self, dns_manager):
        dns_manager.client.delete = Mock(return_value=None)

        dns_manager.delete_zone(12345)

        dns_manager.client.delete.assert_called_once_with("/dnszone/12345")

    def test_add_record(self, dns_manager):
        dns_manager.client.put = Mock(return_value={
            "Id": 99,
            "Type": 0,
            "Name": "www",
            "Value": "1.2.3.4",
            "Ttl": 300,
        })

        record = DNSRecord(type="A", name="www", value="1.2.3.4")
        result = dns_manager.add_record(12345, record)

        dns_manager.client.put.assert_called_once()
        call_args = dns_manager.client.put.call_args
        assert call_args[0][0] == "/dnszone/12345/records"
        assert result.id == 99

    def test_update_record(self, dns_manager):
        dns_manager.client.post = Mock(return_value=None)

        record = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=600)
        dns_manager.update_record(12345, 99, record)

        dns_manager.client.post.assert_called_once()
        call_args = dns_manager.client.post.call_args
        assert call_args[0][0] == "/dnszone/12345/records/99"
        assert call_args[0][1]["Id"] == 99

    def test_delete_record(self, dns_manager):
        dns_manager.client.delete = Mock(return_value=None)

        dns_manager.delete_record(12345, 99)

        dns_manager.client.delete.assert_called_once_with("/dnszone/12345/records/99")


class TestDNSManagerSyncZone:
    """Test sync_zone orchestration logic."""

    @pytest.fixture
    def dns_manager(self, mock_client):
        return DNSManager(mock_client)

    def test_sync_creates_missing_zone(self, dns_manager, sample_dns_zone_response):
        # Zone doesn't exist, then gets created
        dns_manager.get_zone_by_domain = Mock(return_value=None)
        created_zone = DNSZone.from_api_response(sample_dns_zone_response)
        created_zone.records = []  # Fresh zone has no records
        dns_manager.create_zone = Mock(return_value=created_zone)
        dns_manager.add_record = Mock(return_value=DNSRecord(type="A", name="www", value="1.2.3.4", id=1))

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[{"type": "A", "name": "www", "value": "1.2.3.4"}],
        )

        assert result["zone_created"] is True
        assert len(result["created"]) == 1
        dns_manager.create_zone.assert_called_once_with("example.com")

    def test_sync_creates_missing_records(self, dns_manager):
        # Zone exists but has no records
        existing_zone = DNSZone(domain="example.com", id=1, records=[])
        dns_manager.get_zone_by_domain = Mock(return_value=existing_zone)
        dns_manager.add_record = Mock(return_value=DNSRecord(type="A", name="www", value="1.2.3.4", id=1))

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[{"type": "A", "name": "www", "value": "1.2.3.4"}],
        )

        assert len(result["created"]) == 1
        assert "A www -> 1.2.3.4" in result["created"][0]
        dns_manager.add_record.assert_called_once()

    def test_sync_updates_changed_records(self, dns_manager):
        # Zone has a record that needs TTL update
        existing_record = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=300, id=1)
        existing_zone = DNSZone(domain="example.com", id=1, records=[existing_record])
        dns_manager.get_zone_by_domain = Mock(return_value=existing_zone)
        dns_manager.update_record = Mock()

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[{"type": "A", "name": "www", "value": "1.2.3.4", "ttl": 600}],
        )

        assert len(result["updated"]) == 1
        dns_manager.update_record.assert_called_once()

    def test_sync_deletes_extra_records(self, dns_manager):
        # Zone has a record not in config
        extra_record = DNSRecord(type="TXT", name="old", value="delete-me", id=99)
        existing_zone = DNSZone(domain="example.com", id=1, records=[extra_record])
        dns_manager.get_zone_by_domain = Mock(return_value=existing_zone)
        dns_manager.delete_record = Mock()

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[],
            delete_extra=True,
        )

        assert len(result["deleted"]) == 1
        dns_manager.delete_record.assert_called_once_with(1, 99)

    def test_sync_no_delete_mode(self, dns_manager):
        # Zone has extra record but delete_extra=False
        extra_record = DNSRecord(type="TXT", name="old", value="keep-me", id=99)
        existing_zone = DNSZone(domain="example.com", id=1, records=[extra_record])
        dns_manager.get_zone_by_domain = Mock(return_value=existing_zone)
        dns_manager.delete_record = Mock()

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[],
            delete_extra=False,
        )

        assert len(result["deleted"]) == 0
        dns_manager.delete_record.assert_not_called()

    def test_sync_unchanged_records(self, dns_manager):
        # Record already matches desired state
        existing_record = DNSRecord(type="A", name="www", value="1.2.3.4", ttl=300, id=1)
        existing_zone = DNSZone(domain="example.com", id=1, records=[existing_record])
        dns_manager.get_zone_by_domain = Mock(return_value=existing_zone)

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[{"type": "A", "name": "www", "value": "1.2.3.4", "ttl": 300}],
        )

        assert len(result["unchanged"]) == 1
        assert len(result["created"]) == 0
        assert len(result["updated"]) == 0

    def test_sync_dry_run_no_changes(self, dns_manager):
        existing_zone = DNSZone(domain="example.com", id=1, records=[])
        dns_manager.get_zone_by_domain = Mock(return_value=existing_zone)
        dns_manager.add_record = Mock()

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[{"type": "A", "name": "www", "value": "1.2.3.4"}],
            dry_run=True,
        )

        assert len(result["created"]) == 1
        dns_manager.add_record.assert_not_called()

    def test_sync_dry_run_new_zone(self, dns_manager):
        dns_manager.get_zone_by_domain = Mock(return_value=None)
        dns_manager.create_zone = Mock()

        result = dns_manager.sync_zone(
            domain="example.com",
            desired_records=[{"type": "A", "name": "@", "value": "1.2.3.4"}],
            dry_run=True,
        )

        assert result["zone_created"] is True
        assert len(result["created"]) == 1
        dns_manager.create_zone.assert_not_called()

    def test_sync_matches_at_with_empty_string(self, dns_manager):
        """Critical test: Config uses @ but API returns empty string - should match."""
        # API returns record with empty name
        api_record = DNSRecord(type="A", name="", value="1.2.3.4", ttl=300, id=1)
        existing_zone = DNSZone(domain="example.com", id=1, records=[api_record])
        dns_manager.get_zone_by_domain = Mock(return_value=existing_zone)

        result = dns_manager.sync_zone(
            domain="example.com",
            # Config uses @
            desired_records=[{"type": "A", "name": "@", "value": "1.2.3.4", "ttl": 300}],
        )

        # Should recognize as unchanged, not create duplicate
        assert len(result["unchanged"]) == 1
        assert len(result["created"]) == 0
