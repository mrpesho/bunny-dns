"""
Tests for sync.py - Main orchestrator.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

from sync import BunnySync, print_results


class TestBunnySyncInit:
    """Test BunnySync initialization."""

    def test_init_creates_managers(self):
        with patch("sync.BunnyClient") as mock_client_class:
            sync = BunnySync("test-api-key")

            mock_client_class.assert_called_once_with("test-api-key")
            assert sync.dns_manager is not None
            assert sync.pullzone_manager is not None
            assert sync.edge_rules_manager is not None


class TestLoadConfig:
    """Test configuration loading."""

    @pytest.fixture
    def bunny_sync(self):
        with patch("sync.BunnyClient"):
            return BunnySync("test-api-key")

    def test_load_config_from_dict(self, bunny_sync, sample_config):
        result = bunny_sync.load_config(sample_config)
        assert result == sample_config

    def test_load_config_from_json_string(self, bunny_sync):
        # Use a short config that won't be mistaken for a file path
        short_config = {"domains": {"test.com": {"dns_records": []}}}
        json_string = json.dumps(short_config)
        result = bunny_sync.load_config(json_string)
        assert result == short_config

    def test_load_config_from_file(self, bunny_sync, sample_config):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_config, f)
            f.flush()
            filepath = f.name

        try:
            result = bunny_sync.load_config(filepath)
            assert result == sample_config
        finally:
            Path(filepath).unlink()

    def test_load_config_from_path_object(self, bunny_sync, sample_config):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            result = bunny_sync.load_config(filepath)
            assert result == sample_config
        finally:
            filepath.unlink()

    def test_load_config_invalid_type(self, bunny_sync):
        with pytest.raises(ValueError, match="Invalid config type"):
            bunny_sync.load_config(12345)


class TestFilterDomains:
    """Test domain filtering logic."""

    @pytest.fixture
    def bunny_sync(self):
        with patch("sync.BunnyClient"):
            return BunnySync("test-api-key")

    def test_filter_no_filter_returns_all(self, bunny_sync):
        domains = {
            "example.com": {"dns_records": []},
            "test.com": {"dns_records": []},
        }
        result = bunny_sync._filter_domains(domains, None)
        assert result == domains

    def test_filter_exact_match(self, bunny_sync):
        domains = {
            "example.com": {"dns_records": []},
            "test.com": {"dns_records": []},
        }
        result = bunny_sync._filter_domains(domains, "example.com")
        assert len(result) == 1
        assert "example.com" in result

    def test_filter_case_insensitive(self, bunny_sync):
        domains = {
            "Example.COM": {"dns_records": []},
        }
        result = bunny_sync._filter_domains(domains, "example.com")
        assert len(result) == 1

    def test_filter_no_match(self, bunny_sync):
        domains = {
            "example.com": {"dns_records": []},
        }
        result = bunny_sync._filter_domains(domains, "notfound.com")
        assert result == {}


class TestSync:
    """Test main sync orchestration."""

    @pytest.fixture
    def bunny_sync(self):
        with patch("sync.BunnyClient"):
            sync = BunnySync("test-api-key")
            sync.dns_manager = MagicMock()
            sync.pullzone_manager = MagicMock()
            sync.edge_rules_manager = MagicMock()
            return sync

    def test_sync_dns_records(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": ["A @ -> 1.2.3.4"],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": False,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = MagicMock(id=1)
        bunny_sync.edge_rules_manager.sync_rules.return_value = {
            "deleted": [],
            "created": [],
            "changes": [],
        }

        result = bunny_sync.sync(sample_config)

        bunny_sync.dns_manager.sync_zone.assert_called_once()
        assert result["summary"]["dns_records_created"] == 1

    def test_sync_pull_zones(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": [],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": True,
            "updated": False,
            "hostnames_added": ["cdn.example.com"],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = MagicMock(id=1)
        bunny_sync.edge_rules_manager.sync_rules.return_value = {
            "deleted": [],
            "created": ["Block admin"],
            "changes": [],
        }

        result = bunny_sync.sync(sample_config)

        bunny_sync.pullzone_manager.sync_zone.assert_called_once()
        assert result["summary"]["pull_zones_created"] == 1
        assert result["summary"]["hostnames_added"] == 1

    def test_sync_edge_rules(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": [],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": False,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = MagicMock(id=67890)
        bunny_sync.edge_rules_manager.sync_rules.return_value = {
            "deleted": [],
            "created": ["Block admin"],
            "changes": [],
        }

        result = bunny_sync.sync(sample_config)

        bunny_sync.edge_rules_manager.sync_rules.assert_called_once_with(
            zone_id=67890,
            rule_configs=sample_config["domains"]["example.com"]["pull_zones"]["my-cdn"]["edge_rules"],
            dry_run=False,
        )
        assert result["summary"]["edge_rules_created"] == 1

    def test_sync_domain_filter(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": [],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": False,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = MagicMock(id=1)
        bunny_sync.edge_rules_manager.sync_rules.return_value = {
            "deleted": [],
            "created": [],
            "changes": [],
        }

        result = bunny_sync.sync(sample_config, domain="example.com")

        assert result["domain_filter"] == "example.com"

    def test_sync_domain_not_found(self, bunny_sync, sample_config):
        with pytest.raises(ValueError, match="not found in configuration"):
            bunny_sync.sync(sample_config, domain="notfound.com")

    def test_sync_dry_run(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": ["A @ -> 1.2.3.4"],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": False,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = MagicMock(id=1)
        bunny_sync.edge_rules_manager.sync_rules.return_value = {
            "deleted": [],
            "created": [],
            "changes": [],
        }

        result = bunny_sync.sync(sample_config, dry_run=True)

        assert result["dry_run"] is True
        # Verify dry_run was passed to managers
        call_kwargs = bunny_sync.dns_manager.sync_zone.call_args[1]
        assert call_kwargs["dry_run"] is True

    def test_sync_no_delete_mode(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": [],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": False,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = MagicMock(id=1)
        bunny_sync.edge_rules_manager.sync_rules.return_value = {
            "deleted": [],
            "created": [],
            "changes": [],
        }

        bunny_sync.sync(sample_config, delete_extra_records=False)

        call_kwargs = bunny_sync.dns_manager.sync_zone.call_args[1]
        assert call_kwargs["delete_extra"] is False

    def test_sync_skips_edge_rules_if_zone_not_found(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": [],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": True,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = None

        result = bunny_sync.sync(sample_config)

        bunny_sync.edge_rules_manager.sync_rules.assert_not_called()


class TestSyncDNSOnly:
    """Test DNS-only sync mode."""

    @pytest.fixture
    def bunny_sync(self):
        with patch("sync.BunnyClient"):
            sync = BunnySync("test-api-key")
            sync.dns_manager = MagicMock()
            sync.pullzone_manager = MagicMock()
            return sync

    def test_sync_dns_only(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": ["A @ -> 1.2.3.4"],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }

        result = bunny_sync.sync_dns_only(sample_config)

        bunny_sync.dns_manager.sync_zone.assert_called_once()
        bunny_sync.pullzone_manager.sync_zone.assert_not_called()
        assert "dns_zones" in result
        assert "pull_zones" not in result

    def test_sync_dns_only_domain_filter(self, bunny_sync, sample_config):
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": [],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }

        result = bunny_sync.sync_dns_only(sample_config, domain="example.com")

        assert result["domain_filter"] == "example.com"

    def test_sync_dns_only_domain_not_found(self, bunny_sync, sample_config):
        with pytest.raises(ValueError, match="not found"):
            bunny_sync.sync_dns_only(sample_config, domain="notfound.com")


class TestSyncPullzonesOnly:
    """Test Pull Zones-only sync mode."""

    @pytest.fixture
    def bunny_sync(self):
        with patch("sync.BunnyClient"):
            sync = BunnySync("test-api-key")
            sync.dns_manager = MagicMock()
            sync.pullzone_manager = MagicMock()
            sync.edge_rules_manager = MagicMock()
            return sync

    def test_sync_pullzones_only(self, bunny_sync, sample_config):
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": True,
            "updated": False,
            "hostnames_added": ["cdn.example.com"],
            "hostnames_removed": [],
            "changes": [],
        }

        result = bunny_sync.sync_pullzones_only(sample_config)

        bunny_sync.pullzone_manager.sync_zone.assert_called_once()
        bunny_sync.dns_manager.sync_zone.assert_not_called()
        bunny_sync.edge_rules_manager.sync_rules.assert_not_called()
        assert "pull_zones" in result
        assert "dns_zones" not in result

    def test_sync_pullzones_only_domain_filter(self, bunny_sync, sample_config):
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": False,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }

        result = bunny_sync.sync_pullzones_only(sample_config, domain="example.com")

        assert result["domain_filter"] == "example.com"

    def test_sync_pullzones_only_domain_not_found(self, bunny_sync, sample_config):
        with pytest.raises(ValueError, match="not found"):
            bunny_sync.sync_pullzones_only(sample_config, domain="notfound.com")


class TestPrintResults:
    """Test result printing (output formatting)."""

    def test_print_dry_run_banner(self, capsys):
        results = {"dry_run": True, "dns_zones": [], "pull_zones": []}
        print_results(results)
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out

    def test_print_domain_filter(self, capsys):
        results = {"domain_filter": "example.com", "dns_zones": [], "pull_zones": []}
        print_results(results)
        captured = capsys.readouterr()
        assert "example.com" in captured.out

    def test_print_dns_zones(self, capsys):
        results = {
            "dns_zones": [{
                "zone": "example.com",
                "zone_created": True,
                "created": ["A www -> 1.2.3.4"],
                "updated": ["A api -> 5.6.7.8"],
                "deleted": ["TXT old -> delete"],
                "unchanged": ["MX @ -> mail.example.com"],
            }],
        }
        print_results(results)
        captured = capsys.readouterr()
        assert "DNS ZONES" in captured.out
        assert "example.com" in captured.out
        assert "NEW ZONE CREATED" in captured.out
        assert "Created: 1 records" in captured.out
        assert "+ A www" in captured.out
        assert "~ A api" in captured.out
        assert "- TXT old" in captured.out

    def test_print_pull_zones(self, capsys):
        results = {
            "pull_zones": [{
                "zone": "my-cdn",
                "created": True,
                "updated": False,
                "changes": ["Adding hostname: cdn.example.com"],
                "edge_rules": {
                    "deleted": ["Old rule"],
                    "created": ["New rule"],
                },
            }],
        }
        print_results(results)
        captured = capsys.readouterr()
        assert "PULL ZONES" in captured.out
        assert "my-cdn" in captured.out
        assert "NEW ZONE CREATED" in captured.out
        assert "Adding hostname" in captured.out
        assert "Edge rules deleted: 1" in captured.out
        assert "Edge rules created: 1" in captured.out

    def test_print_summary(self, capsys):
        results = {
            "summary": {
                "dns_records_created": 2,
                "dns_records_updated": 1,
                "dns_records_deleted": 0,
                "pull_zones_created": 1,
                "pull_zones_updated": 0,
                "hostnames_added": 2,
                "hostnames_removed": 1,
                "edge_rules_created": 3,
                "edge_rules_deleted": 2,
            },
        }
        print_results(results)
        captured = capsys.readouterr()
        assert "SUMMARY" in captured.out
        assert "DNS records: 2 created" in captured.out
        assert "Pull zones: 1 created" in captured.out
        assert "Hostnames: 2 added" in captured.out
        assert "Edge rules: 3 created" in captured.out


class TestIntegration:
    """Integration tests with realistic config scenarios."""

    @pytest.fixture
    def bunny_sync(self):
        with patch("sync.BunnyClient"):
            sync = BunnySync("test-api-key")
            sync.dns_manager = MagicMock()
            sync.pullzone_manager = MagicMock()
            sync.edge_rules_manager = MagicMock()
            return sync

    def test_empty_config(self, bunny_sync):
        config = {"domains": {}}
        result = bunny_sync.sync(config)

        assert result["dns_zones"] == []
        assert result["pull_zones"] == []

    def test_domain_without_dns_records(self, bunny_sync):
        config = {
            "domains": {
                "example.com": {
                    "pull_zones": {
                        "my-cdn": {
                            "origin_url": "https://origin.example.com",
                        }
                    }
                }
            }
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": True,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = None

        result = bunny_sync.sync(config)

        bunny_sync.dns_manager.sync_zone.assert_not_called()
        bunny_sync.pullzone_manager.sync_zone.assert_called_once()

    def test_domain_without_pull_zones(self, bunny_sync):
        config = {
            "domains": {
                "example.com": {
                    "dns_records": [
                        {"type": "A", "name": "@", "value": "1.2.3.4"},
                    ]
                }
            }
        }
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "example.com",
            "created": ["A @ -> 1.2.3.4"],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }

        result = bunny_sync.sync(config)

        bunny_sync.dns_manager.sync_zone.assert_called_once()
        bunny_sync.pullzone_manager.sync_zone.assert_not_called()

    def test_pull_zone_without_edge_rules(self, bunny_sync):
        config = {
            "domains": {
                "example.com": {
                    "dns_records": [],
                    "pull_zones": {
                        "my-cdn": {
                            "origin_url": "https://origin.example.com",
                            # No edge_rules key
                        }
                    }
                }
            }
        }
        bunny_sync.pullzone_manager.sync_zone.return_value = {
            "zone": "my-cdn",
            "created": True,
            "updated": False,
            "hostnames_added": [],
            "hostnames_removed": [],
            "changes": [],
        }
        bunny_sync.pullzone_manager.get_zone_by_name.return_value = MagicMock(id=1)

        result = bunny_sync.sync(config)

        bunny_sync.edge_rules_manager.sync_rules.assert_not_called()

    def test_multiple_domains(self, bunny_sync):
        config = {
            "domains": {
                "example.com": {
                    "dns_records": [{"type": "A", "name": "@", "value": "1.2.3.4"}],
                },
                "test.com": {
                    "dns_records": [{"type": "A", "name": "@", "value": "5.6.7.8"}],
                },
            }
        }
        bunny_sync.dns_manager.sync_zone.return_value = {
            "zone": "test",
            "created": [],
            "updated": [],
            "deleted": [],
            "unchanged": [],
        }

        result = bunny_sync.sync(config)

        assert bunny_sync.dns_manager.sync_zone.call_count == 2
