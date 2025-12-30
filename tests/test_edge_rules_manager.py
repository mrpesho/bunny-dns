"""
Tests for edge_rules_manager.py - Edge Rules management.
"""

from unittest.mock import Mock, MagicMock

import pytest

from edge_rules_manager import (
    ACTION_TYPES,
    ACTION_TYPES_REVERSE,
    TRIGGER_TYPES,
    TRIGGER_TYPES_REVERSE,
    MATCH_TYPES,
    EdgeRuleTrigger,
    EdgeRuleAction,
    EdgeRule,
    parse_action_from_config,
    parse_trigger_from_config,
    parse_rule_from_config,
    EdgeRulesManager,
)


class TestActionTypes:
    """Test action type mappings."""

    def test_all_action_types_defined(self):
        expected_actions = [
            "force_ssl", "redirect", "origin_url", "override_cache_time",
            "block", "set_response_header", "set_request_header", "force_download",
            "disable_token_auth", "enable_token_auth", "override_cache_time_public",
            "ignore_query_string", "disable_optimizer", "force_compression",
            "set_status_code", "bypass_perma_cache",
        ]
        for action in expected_actions:
            assert action in ACTION_TYPES

    def test_action_type_values(self):
        assert ACTION_TYPES["force_ssl"] == 0
        assert ACTION_TYPES["redirect"] == 1
        assert ACTION_TYPES["block"] == 4
        assert ACTION_TYPES["set_response_header"] == 5
        assert ACTION_TYPES["set_request_header"] == 6

    def test_reverse_mapping(self):
        for name, value in ACTION_TYPES.items():
            assert ACTION_TYPES_REVERSE[value] == name


class TestTriggerTypes:
    """Test trigger type mappings."""

    def test_all_trigger_types_defined(self):
        expected_triggers = [
            "url", "request_header", "response_header", "url_extension",
            "country_code", "remote_ip", "url_query_string", "random_chance",
            "status_code", "request_method",
        ]
        for trigger in expected_triggers:
            assert trigger in TRIGGER_TYPES

    def test_trigger_type_values(self):
        assert TRIGGER_TYPES["url"] == 0
        assert TRIGGER_TYPES["request_header"] == 1
        assert TRIGGER_TYPES["country_code"] == 4
        assert TRIGGER_TYPES["request_method"] == 9

    def test_reverse_mapping(self):
        for name, value in TRIGGER_TYPES.items():
            assert TRIGGER_TYPES_REVERSE[value] == name


class TestMatchTypes:
    """Test match type mappings."""

    def test_match_type_values(self):
        assert MATCH_TYPES["any"] == 0
        assert MATCH_TYPES["all"] == 1
        assert MATCH_TYPES["none"] == 2


class TestEdgeRuleTrigger:
    """Test EdgeRuleTrigger dataclass."""

    def test_default_values(self):
        trigger = EdgeRuleTrigger(type="url")
        assert trigger.patterns == []
        assert trigger.match == "any"
        assert trigger.parameter is None

    def test_to_api_payload_basic(self):
        trigger = EdgeRuleTrigger(type="url", patterns=["/admin/*"])
        payload = trigger.to_api_payload()

        assert payload["Type"] == 0
        assert payload["PatternMatches"] == ["/admin/*"]
        assert payload["PatternMatchingType"] == 0
        assert "Parameter1" not in payload

    def test_to_api_payload_with_parameter(self):
        trigger = EdgeRuleTrigger(
            type="request_header",
            patterns=["curl/*"],
            match="any",
            parameter="User-Agent",
        )
        payload = trigger.to_api_payload()

        assert payload["Type"] == 1
        assert payload["Parameter1"] == "User-Agent"

    def test_to_api_payload_all_match(self):
        trigger = EdgeRuleTrigger(type="url", patterns=["/api/*"], match="all")
        payload = trigger.to_api_payload()

        assert payload["PatternMatchingType"] == 1

    def test_from_api_response(self, sample_edge_rule_response):
        trigger_data = sample_edge_rule_response["Triggers"][0]
        trigger = EdgeRuleTrigger.from_api_response(trigger_data)

        assert trigger.type == "url"
        assert trigger.patterns == ["/admin/*"]
        assert trigger.match == "any"

    def test_from_api_response_with_parameter(self):
        data = {
            "Type": 1,  # request_header
            "PatternMatches": ["curl/*"],
            "PatternMatchingType": 0,
            "Parameter1": "User-Agent",
        }
        trigger = EdgeRuleTrigger.from_api_response(data)

        assert trigger.type == "request_header"
        assert trigger.parameter == "User-Agent"


class TestEdgeRuleAction:
    """Test EdgeRuleAction dataclass."""

    def test_default_values(self):
        action = EdgeRuleAction(type="block")
        assert action.parameter1 is None
        assert action.parameter2 is None

    def test_to_api_payload_simple(self):
        action = EdgeRuleAction(type="block")
        payload = action.to_api_payload()

        assert payload["ActionType"] == 4
        assert "ActionParameter1" not in payload
        assert "ActionParameter2" not in payload

    def test_to_api_payload_with_parameters(self):
        action = EdgeRuleAction(
            type="set_response_header",
            parameter1="X-Custom",
            parameter2="value",
        )
        payload = action.to_api_payload()

        assert payload["ActionType"] == 5
        assert payload["ActionParameter1"] == "X-Custom"
        assert payload["ActionParameter2"] == "value"


class TestEdgeRule:
    """Test EdgeRule dataclass."""

    def test_default_values(self):
        rule = EdgeRule(description="Test rule")
        assert rule.enabled is True
        assert rule.triggers == []
        assert rule.actions == []
        assert rule.trigger_match == "all"
        assert rule.guid is None

    def test_to_api_payload(self):
        trigger = EdgeRuleTrigger(type="url", patterns=["/admin/*"])
        action = EdgeRuleAction(type="block")
        rule = EdgeRule(
            description="Block admin",
            triggers=[trigger],
            actions=[action],
        )
        payload = rule.to_api_payload()

        assert payload["Description"] == "Block admin"
        assert payload["Enabled"] is True
        assert payload["ActionType"] == 4
        assert len(payload["Triggers"]) == 1
        assert payload["TriggerMatchingType"] == 1  # all

    def test_to_api_payload_with_guid(self):
        action = EdgeRuleAction(type="block")
        rule = EdgeRule(
            description="Test",
            actions=[action],
            guid="abc-123",
        )
        payload = rule.to_api_payload()

        assert payload["Guid"] == "abc-123"

    def test_to_api_payload_empty_actions(self):
        rule = EdgeRule(description="Empty")
        payload = rule.to_api_payload()

        assert payload == {}

    def test_to_api_payload_redirect_with_parameters(self):
        action = EdgeRuleAction(
            type="redirect",
            parameter1="https://example.com/new",
            parameter2="301",
        )
        rule = EdgeRule(description="Redirect", actions=[action])
        payload = rule.to_api_payload()

        assert payload["ActionType"] == 1
        assert payload["ActionParameter1"] == "https://example.com/new"
        assert payload["ActionParameter2"] == "301"

    def test_from_api_response(self, sample_edge_rule_response):
        rule = EdgeRule.from_api_response(sample_edge_rule_response)

        assert rule.guid == "abc-123-def"
        assert rule.description == "Block admin access"
        assert rule.enabled is True
        assert len(rule.triggers) == 1
        assert len(rule.actions) == 1
        assert rule.actions[0].type == "block"
        assert rule.trigger_match == "all"


class TestParseActionFromConfig:
    """Test action parsing from config format."""

    def test_parse_block_action(self):
        action = parse_action_from_config({"type": "block"})
        assert action.type == "block"
        assert action.parameter1 is None

    def test_parse_force_ssl_action(self):
        action = parse_action_from_config({"type": "force_ssl"})
        assert action.type == "force_ssl"

    def test_parse_set_response_header(self):
        action = parse_action_from_config({
            "type": "set_response_header",
            "header": "X-Custom",
            "value": "my-value",
        })
        assert action.type == "set_response_header"
        assert action.parameter1 == "X-Custom"
        assert action.parameter2 == "my-value"

    def test_parse_set_request_header(self):
        action = parse_action_from_config({
            "type": "set_request_header",
            "header": "X-Forwarded-For",
            "value": "client-ip",
        })
        assert action.type == "set_request_header"
        assert action.parameter1 == "X-Forwarded-For"
        assert action.parameter2 == "client-ip"

    def test_parse_redirect_action(self):
        action = parse_action_from_config({
            "type": "redirect",
            "url": "https://example.com/new",
            "status_code": "302",
        })
        assert action.type == "redirect"
        assert action.parameter1 == "https://example.com/new"
        assert action.parameter2 == "302"

    def test_parse_redirect_default_status(self):
        action = parse_action_from_config({
            "type": "redirect",
            "url": "https://example.com/new",
        })
        assert action.parameter2 == "301"  # Default

    def test_parse_origin_url_action(self):
        action = parse_action_from_config({
            "type": "origin_url",
            "url": "https://new-origin.example.com",
        })
        assert action.type == "origin_url"
        assert action.parameter1 == "https://new-origin.example.com"

    def test_parse_override_cache_time(self):
        action = parse_action_from_config({
            "type": "override_cache_time",
            "seconds": 3600,
        })
        assert action.type == "override_cache_time"
        assert action.parameter1 == "3600"

    def test_parse_override_cache_time_default(self):
        action = parse_action_from_config({"type": "override_cache_time"})
        assert action.parameter1 == "0"

    def test_parse_set_status_code(self):
        action = parse_action_from_config({
            "type": "set_status_code",
            "code": 404,
        })
        assert action.type == "set_status_code"
        assert action.parameter1 == "404"


class TestParseTriggerFromConfig:
    """Test trigger parsing from config format."""

    def test_parse_url_trigger(self):
        trigger = parse_trigger_from_config({
            "type": "url",
            "patterns": ["/admin/*", "/private/*"],
            "match": "any",
        })
        assert trigger.type == "url"
        assert trigger.patterns == ["/admin/*", "/private/*"]
        assert trigger.match == "any"

    def test_parse_trigger_defaults(self):
        trigger = parse_trigger_from_config({})
        assert trigger.type == "url"
        assert trigger.patterns == []
        assert trigger.match == "any"

    def test_parse_request_header_trigger(self):
        trigger = parse_trigger_from_config({
            "type": "request_header",
            "patterns": ["bot*"],
            "parameter": "User-Agent",
        })
        assert trigger.type == "request_header"
        assert trigger.parameter == "User-Agent"

    def test_parse_country_code_trigger(self):
        trigger = parse_trigger_from_config({
            "type": "country_code",
            "patterns": ["US", "CA", "GB"],
            "match": "none",
        })
        assert trigger.type == "country_code"
        assert trigger.patterns == ["US", "CA", "GB"]
        assert trigger.match == "none"


class TestParseRuleFromConfig:
    """Test full rule parsing with action expansion."""

    def test_parse_single_action_rule(self):
        config = {
            "description": "Block admin",
            "enabled": True,
            "trigger_match": "all",
            "triggers": [{"type": "url", "patterns": ["/admin/*"]}],
            "actions": [{"type": "block"}],
        }
        rules = parse_rule_from_config(config)

        assert len(rules) == 1
        assert rules[0].description == "Block admin"
        assert len(rules[0].triggers) == 1
        assert len(rules[0].actions) == 1

    def test_parse_multi_action_rule_expands(self):
        """Critical test: Multiple actions should create multiple rules."""
        config = {
            "description": "Add headers",
            "triggers": [{"type": "url", "patterns": ["/*"]}],
            "actions": [
                {"type": "set_response_header", "header": "X-One", "value": "1"},
                {"type": "set_response_header", "header": "X-Two", "value": "2"},
            ],
        }
        rules = parse_rule_from_config(config)

        assert len(rules) == 2
        assert rules[0].description == "Add headers (action 1)"
        assert rules[1].description == "Add headers (action 2)"
        assert rules[0].actions[0].parameter1 == "X-One"
        assert rules[1].actions[0].parameter1 == "X-Two"

    def test_parse_rule_shares_triggers(self):
        """When expanding to multiple rules, triggers should be shared."""
        config = {
            "description": "Multi-action",
            "triggers": [
                {"type": "url", "patterns": ["/api/*"]},
                {"type": "request_method", "patterns": ["POST"]},
            ],
            "actions": [
                {"type": "block"},
                {"type": "force_ssl"},
            ],
        }
        rules = parse_rule_from_config(config)

        assert len(rules) == 2
        # Both rules have same triggers
        assert len(rules[0].triggers) == 2
        assert len(rules[1].triggers) == 2

    def test_parse_rule_default_values(self):
        config = {
            "description": "Minimal",
            "triggers": [{"type": "url", "patterns": ["/*"]}],
            "actions": [{"type": "block"}],
        }
        rules = parse_rule_from_config(config)

        assert rules[0].enabled is True
        assert rules[0].trigger_match == "all"

    def test_parse_rule_disabled(self):
        config = {
            "description": "Disabled rule",
            "enabled": False,
            "triggers": [{"type": "url", "patterns": ["/*"]}],
            "actions": [{"type": "block"}],
        }
        rules = parse_rule_from_config(config)

        assert rules[0].enabled is False


class TestEdgeRulesManager:
    """Test EdgeRulesManager API interactions."""

    @pytest.fixture
    def er_manager(self, mock_client):
        return EdgeRulesManager(mock_client)

    def test_get_rules(self, er_manager, sample_edge_rule_response):
        er_manager.client.get = Mock(return_value={
            "EdgeRules": [sample_edge_rule_response],
        })

        rules = er_manager.get_rules(67890)

        er_manager.client.get.assert_called_once_with("/pullzone/67890")
        assert len(rules) == 1
        assert rules[0].description == "Block admin access"

    def test_get_rules_empty(self, er_manager):
        er_manager.client.get = Mock(return_value={"EdgeRules": []})

        rules = er_manager.get_rules(67890)

        assert rules == []

    def test_get_rules_none_response(self, er_manager):
        er_manager.client.get = Mock(return_value=None)

        rules = er_manager.get_rules(67890)

        assert rules == []

    def test_add_or_update_rule(self, er_manager):
        er_manager.client.post = Mock(return_value={"Guid": "new-guid"})

        action = EdgeRuleAction(type="block")
        rule = EdgeRule(description="Test", actions=[action])
        result = er_manager.add_or_update_rule(67890, rule)

        er_manager.client.post.assert_called_once()
        call_args = er_manager.client.post.call_args
        assert call_args[0][0] == "/pullzone/67890/edgerules/addOrUpdate"
        assert result["Guid"] == "new-guid"

    def test_delete_rule(self, er_manager):
        er_manager.client.delete = Mock(return_value=None)

        er_manager.delete_rule(67890, "abc-123")

        er_manager.client.delete.assert_called_once_with("/pullzone/67890/edgerules/abc-123")

    def test_delete_all_rules(self, er_manager, sample_edge_rule_response):
        er_manager.get_rules = Mock(return_value=[
            EdgeRule.from_api_response(sample_edge_rule_response),
        ])
        er_manager.delete_rule = Mock()

        er_manager.delete_all_rules(67890)

        er_manager.delete_rule.assert_called_once_with(67890, "abc-123-def")


class TestEdgeRulesManagerSyncRules:
    """Test sync_rules orchestration logic."""

    @pytest.fixture
    def er_manager(self, mock_client):
        return EdgeRulesManager(mock_client)

    def test_sync_deletes_existing_and_creates_new(self, er_manager, sample_edge_rule_response):
        existing_rule = EdgeRule.from_api_response(sample_edge_rule_response)
        er_manager.get_rules = Mock(return_value=[existing_rule])
        er_manager.delete_rule = Mock()
        er_manager.add_or_update_rule = Mock(return_value={"Guid": "new-guid"})

        result = er_manager.sync_rules(
            zone_id=67890,
            rule_configs=[{
                "description": "New rule",
                "triggers": [{"type": "url", "patterns": ["/*"]}],
                "actions": [{"type": "force_ssl"}],
            }],
        )

        assert len(result["deleted"]) == 1
        assert len(result["created"]) == 1
        er_manager.delete_rule.assert_called_once()
        er_manager.add_or_update_rule.assert_called_once()

    def test_sync_empty_config_deletes_all(self, er_manager, sample_edge_rule_response):
        existing_rule = EdgeRule.from_api_response(sample_edge_rule_response)
        er_manager.get_rules = Mock(return_value=[existing_rule])
        er_manager.delete_rule = Mock()

        result = er_manager.sync_rules(zone_id=67890, rule_configs=[])

        assert len(result["deleted"]) == 1
        assert len(result["created"]) == 0
        er_manager.delete_rule.assert_called_once()

    def test_sync_creates_from_empty(self, er_manager):
        er_manager.get_rules = Mock(return_value=[])
        er_manager.add_or_update_rule = Mock(return_value={})

        result = er_manager.sync_rules(
            zone_id=67890,
            rule_configs=[{
                "description": "New rule",
                "triggers": [{"type": "url", "patterns": ["/*"]}],
                "actions": [{"type": "block"}],
            }],
        )

        assert len(result["deleted"]) == 0
        assert len(result["created"]) == 1
        er_manager.add_or_update_rule.assert_called_once()

    def test_sync_multi_action_creates_multiple_rules(self, er_manager):
        er_manager.get_rules = Mock(return_value=[])
        er_manager.add_or_update_rule = Mock(return_value={})

        result = er_manager.sync_rules(
            zone_id=67890,
            rule_configs=[{
                "description": "Multi",
                "triggers": [{"type": "url", "patterns": ["/*"]}],
                "actions": [
                    {"type": "force_ssl"},
                    {"type": "set_response_header", "header": "X-Test", "value": "1"},
                ],
            }],
        )

        assert len(result["created"]) == 2
        assert er_manager.add_or_update_rule.call_count == 2

    def test_sync_dry_run_no_changes(self, er_manager, sample_edge_rule_response):
        existing_rule = EdgeRule.from_api_response(sample_edge_rule_response)
        er_manager.get_rules = Mock(return_value=[existing_rule])
        er_manager.delete_rule = Mock()
        er_manager.add_or_update_rule = Mock()

        result = er_manager.sync_rules(
            zone_id=67890,
            rule_configs=[{
                "description": "New",
                "triggers": [{"type": "url", "patterns": ["/*"]}],
                "actions": [{"type": "block"}],
            }],
            dry_run=True,
        )

        assert len(result["deleted"]) == 1
        assert len(result["created"]) == 1
        er_manager.delete_rule.assert_not_called()
        er_manager.add_or_update_rule.assert_not_called()

    def test_sync_tracks_changes(self, er_manager):
        er_manager.get_rules = Mock(return_value=[])
        er_manager.add_or_update_rule = Mock(return_value={})

        result = er_manager.sync_rules(
            zone_id=67890,
            rule_configs=[{
                "description": "Test rule",
                "triggers": [{"type": "url", "patterns": ["/*"]}],
                "actions": [{"type": "block"}],
            }],
        )

        assert any("Creating rule: Test rule" in c for c in result["changes"])
