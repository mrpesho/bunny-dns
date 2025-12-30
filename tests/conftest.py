"""
Shared fixtures for bunny-dns-sync tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

# Add parent directory to path so we can import the modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from bunny_client import BunnyClient


@pytest.fixture
def mock_session():
    """Create a mock requests session."""
    return MagicMock()


@pytest.fixture
def mock_client(mock_session):
    """Create a BunnyClient with mocked session."""
    client = BunnyClient(api_key="test-api-key")
    client.session = mock_session
    return client


@pytest.fixture
def mock_response():
    """Factory fixture for creating mock responses."""
    def _create_response(status_code=200, json_data=None, text=""):
        response = Mock()
        response.status_code = status_code
        response.text = text if text else (str(json_data) if json_data else "")
        response.json = Mock(return_value=json_data)
        return response
    return _create_response


@pytest.fixture
def sample_dns_zone_response():
    """Sample DNS zone response from API."""
    return {
        "Id": 12345,
        "Domain": "example.com",
        "Records": [
            {
                "Id": 1,
                "Type": 0,  # A record
                "Name": "",
                "Value": "1.2.3.4",
                "Ttl": 300,
                "Priority": 0,
                "Weight": 0,
                "Port": 0,
            },
            {
                "Id": 2,
                "Type": 2,  # CNAME
                "Name": "www",
                "Value": "example.com",
                "Ttl": 300,
                "Priority": 0,
                "Weight": 0,
                "Port": 0,
            },
            {
                "Id": 3,
                "Type": 4,  # MX
                "Name": "",
                "Value": "mail.example.com",
                "Ttl": 300,
                "Priority": 10,
                "Weight": 0,
                "Port": 0,
            },
        ],
    }


@pytest.fixture
def sample_pullzone_response():
    """Sample Pull Zone response from API."""
    return {
        "Id": 67890,
        "Name": "my-cdn",
        "OriginUrl": "https://origin.example.com",
        "OriginHostHeader": "origin.example.com",
        "Type": 0,
        "Enabled": True,
        "EnableGeoZoneUS": True,
        "EnableGeoZoneEU": True,
        "EnableGeoZoneASIA": True,
        "EnableGeoZoneSA": False,
        "EnableGeoZoneAF": False,
        "Hostnames": [
            {
                "Id": 1,
                "Value": "my-cdn.b-cdn.net",
                "ForceSSL": True,
                "HasCertificate": True,
                "IsSystemHostname": True,
            },
            {
                "Id": 2,
                "Value": "cdn.example.com",
                "ForceSSL": True,
                "HasCertificate": True,
                "IsSystemHostname": False,
            },
        ],
        "EdgeRules": [],
    }


@pytest.fixture
def sample_edge_rule_response():
    """Sample Edge Rule response from API."""
    return {
        "Guid": "abc-123-def",
        "ActionType": 4,  # block
        "ActionParameter1": None,
        "ActionParameter2": None,
        "Triggers": [
            {
                "Type": 0,  # url
                "PatternMatches": ["/admin/*"],
                "PatternMatchingType": 0,  # any
                "Parameter1": None,
            }
        ],
        "TriggerMatchingType": 1,  # all
        "Description": "Block admin access",
        "Enabled": True,
    }


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "domains": {
            "example.com": {
                "dns_records": [
                    {"type": "A", "name": "@", "value": "1.2.3.4", "ttl": 300},
                    {"type": "CNAME", "name": "www", "value": "example.com", "ttl": 300},
                    {"type": "MX", "name": "@", "value": "mail.example.com", "ttl": 300, "priority": 10},
                ],
                "pull_zones": {
                    "my-cdn": {
                        "origin_url": "https://origin.example.com",
                        "origin_host_header": "origin.example.com",
                        "type": "standard",
                        "enabled_regions": ["EU", "US", "ASIA"],
                        "hostnames": ["cdn.example.com"],
                        "edge_rules": [
                            {
                                "description": "Block admin",
                                "enabled": True,
                                "trigger_match": "all",
                                "triggers": [
                                    {"type": "url", "patterns": ["/admin/*"], "match": "any"}
                                ],
                                "actions": [{"type": "block"}],
                            }
                        ],
                    }
                },
            }
        }
    }
