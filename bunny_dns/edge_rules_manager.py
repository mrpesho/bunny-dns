"""
Edge Rules management for bunny.net Pull Zones.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from .bunny_client import BunnyClient


# Edge Rule Action Types
ACTION_TYPES = {
    "force_ssl": 0,
    "redirect": 1,
    "origin_url": 2,
    "override_cache_time": 3,
    "block": 4,
    "set_response_header": 5,
    "set_request_header": 6,
    "force_download": 7,
    "disable_token_auth": 8,
    "enable_token_auth": 9,
    "override_cache_time_public": 10,
    "ignore_query_string": 11,
    "disable_optimizer": 12,
    "force_compression": 13,
    "set_status_code": 14,
    "bypass_perma_cache": 15,
}

ACTION_TYPES_REVERSE = {v: k for k, v in ACTION_TYPES.items()}

# Edge Rule Trigger Types
TRIGGER_TYPES = {
    "url": 0,
    "request_header": 1,
    "response_header": 2,
    "url_extension": 3,
    "country_code": 4,
    "remote_ip": 5,
    "url_query_string": 6,
    "random_chance": 7,
    "status_code": 8,
    "request_method": 9,
}

TRIGGER_TYPES_REVERSE = {v: k for k, v in TRIGGER_TYPES.items()}

# Pattern Matching Types
MATCH_TYPES = {
    "any": 0,
    "all": 1,
    "none": 2,
}


@dataclass
class EdgeRuleTrigger:
    """Represents an edge rule trigger."""
    type: str
    patterns: list[str] = field(default_factory=list)
    match: str = "any"  # any, all, none
    parameter: Optional[str] = None  # For header name, etc.

    def to_config_dict(self) -> dict:
        """Convert to config format (inverse of parse_trigger_from_config)."""
        d = {
            "type": self.type,
            "patterns": list(self.patterns),
            "match": self.match,
        }
        if self.parameter:
            d["parameter"] = self.parameter
        return d

    def to_api_payload(self) -> dict:
        payload = {
            "Type": TRIGGER_TYPES.get(self.type, 0),
            "PatternMatches": self.patterns,
            "PatternMatchingType": MATCH_TYPES.get(self.match, 0),
        }
        if self.parameter:
            payload["Parameter1"] = self.parameter
        return payload

    @classmethod
    def from_api_response(cls, data: dict) -> "EdgeRuleTrigger":
        trigger_type = TRIGGER_TYPES_REVERSE.get(data.get("Type", 0), "url")
        match_type = "any"
        for name, value in MATCH_TYPES.items():
            if value == data.get("PatternMatchingType", 0):
                match_type = name
                break
        return cls(
            type=trigger_type,
            patterns=data.get("PatternMatches", []),
            match=match_type,
            parameter=data.get("Parameter1"),
        )


@dataclass
class EdgeRuleAction:
    """Represents an edge rule action."""
    type: str
    parameter1: Optional[str] = None  # Header name, redirect URL, etc.
    parameter2: Optional[str] = None  # Header value, etc.

    def to_config_dict(self) -> dict:
        """Convert to config format (inverse of parse_action_from_config)."""
        if self.type in ("set_response_header", "set_request_header"):
            return {
                "type": self.type,
                "header": self.parameter1 or "",
                "value": self.parameter2 or "",
            }
        elif self.type == "redirect":
            return {
                "type": self.type,
                "url": self.parameter1 or "",
                "status_code": self.parameter2 or "301",
            }
        elif self.type == "origin_url":
            return {
                "type": self.type,
                "url": self.parameter1 or "",
            }
        elif self.type == "override_cache_time":
            return {
                "type": self.type,
                "seconds": int(self.parameter1) if self.parameter1 else 0,
            }
        elif self.type == "set_status_code":
            return {
                "type": self.type,
                "code": int(self.parameter1) if self.parameter1 else 200,
            }
        else:
            return {"type": self.type}

    def to_api_payload(self) -> dict:
        payload = {
            "ActionType": ACTION_TYPES.get(self.type, 0),
        }
        if self.parameter1 is not None:
            payload["ActionParameter1"] = self.parameter1
        if self.parameter2 is not None:
            payload["ActionParameter2"] = self.parameter2
        return payload


@dataclass
class EdgeRule:
    """Represents an edge rule."""
    description: str
    enabled: bool = True
    triggers: list[EdgeRuleTrigger] = field(default_factory=list)
    actions: list[EdgeRuleAction] = field(default_factory=list)
    trigger_match: str = "all"  # any, all, none
    guid: Optional[str] = None

    def to_api_payload(self) -> dict:
        """Convert to API payload. Note: Creates one rule per action."""
        # The API expects ActionType, ActionParameter1, ActionParameter2 at the root level
        # For multiple actions, we need to create multiple rules or use the new multi-action format
        if not self.actions:
            return {}

        # Use first action for the main rule payload
        action = self.actions[0]
        payload = {
            "ActionType": ACTION_TYPES.get(action.type, 0),
            "Triggers": [t.to_api_payload() for t in self.triggers],
            "TriggerMatchingType": MATCH_TYPES.get(self.trigger_match, 1),
            "Description": self.description,
            "Enabled": self.enabled,
        }
        if action.parameter1 is not None:
            payload["ActionParameter1"] = action.parameter1
        if action.parameter2 is not None:
            payload["ActionParameter2"] = action.parameter2
        if self.guid:
            payload["Guid"] = self.guid
        return payload

    @classmethod
    def from_api_response(cls, data: dict) -> "EdgeRule":
        triggers = [
            EdgeRuleTrigger.from_api_response(t)
            for t in data.get("Triggers", [])
        ]
        action_type = ACTION_TYPES_REVERSE.get(data.get("ActionType", 0), "block")
        actions = [
            EdgeRuleAction(
                type=action_type,
                parameter1=data.get("ActionParameter1"),
                parameter2=data.get("ActionParameter2"),
            )
        ]
        trigger_match = "all"
        for name, value in MATCH_TYPES.items():
            if value == data.get("TriggerMatchingType", 1):
                trigger_match = name
                break
        return cls(
            guid=data.get("Guid"),
            description=data.get("Description", ""),
            enabled=data.get("Enabled", True),
            triggers=triggers,
            actions=actions,
            trigger_match=trigger_match,
        )


def parse_action_from_config(action_config: dict) -> EdgeRuleAction:
    """Parse an action from config format."""
    action_type = action_config.get("type", "block")

    # Handle different action types
    if action_type in ("set_response_header", "set_request_header"):
        return EdgeRuleAction(
            type=action_type,
            parameter1=action_config.get("header"),
            parameter2=action_config.get("value"),
        )
    elif action_type == "redirect":
        return EdgeRuleAction(
            type=action_type,
            parameter1=action_config.get("url"),
            parameter2=action_config.get("status_code", "301"),
        )
    elif action_type == "origin_url":
        return EdgeRuleAction(
            type=action_type,
            parameter1=action_config.get("url"),
        )
    elif action_type == "override_cache_time":
        return EdgeRuleAction(
            type=action_type,
            parameter1=str(action_config.get("seconds", 0)),
        )
    elif action_type == "set_status_code":
        return EdgeRuleAction(
            type=action_type,
            parameter1=str(action_config.get("code", 200)),
        )
    else:
        return EdgeRuleAction(type=action_type)


def parse_trigger_from_config(trigger_config: dict) -> EdgeRuleTrigger:
    """Parse a trigger from config format."""
    return EdgeRuleTrigger(
        type=trigger_config.get("type", "url"),
        patterns=trigger_config.get("patterns", []),
        match=trigger_config.get("match", "any"),
        parameter=trigger_config.get("parameter"),
    )


def parse_rule_from_config(rule_config: dict) -> list[EdgeRule]:
    """
    Parse an edge rule from config format.
    Returns a list of rules (one per action, since API requires separate rules).
    """
    triggers = [
        parse_trigger_from_config(t)
        for t in rule_config.get("triggers", [])
    ]
    actions = [
        parse_action_from_config(a)
        for a in rule_config.get("actions", [])
    ]

    # Create one rule per action (API limitation)
    rules = []
    for i, action in enumerate(actions):
        desc = rule_config.get("description", "Edge Rule")
        if len(actions) > 1:
            desc = f"{desc} (action {i + 1})"
        rules.append(EdgeRule(
            description=desc,
            enabled=rule_config.get("enabled", True),
            triggers=triggers,
            actions=[action],
            trigger_match=rule_config.get("trigger_match", "all"),
        ))
    return rules


import re


def group_api_rules_to_config(rules: list[EdgeRule]) -> list[dict]:
    """Group API rules (1 action each) back into multi-action config rules.

    Rules created from multi-action configs have descriptions like
    "My Rule (action 1)", "My Rule (action 2)". This groups them back
    by stripping the suffix and matching on base description + triggers + enabled.
    """
    # Build groups: key = (base_description, enabled, trigger_match, triggers_repr)
    groups: dict[tuple, list[EdgeRule]] = {}
    action_suffix_re = re.compile(r" \(action \d+\)$")

    for rule in rules:
        base_desc = action_suffix_re.sub("", rule.description)
        triggers_key = tuple(
            (t.type, tuple(t.patterns), t.match, t.parameter or "")
            for t in rule.triggers
        )
        key = (base_desc, rule.enabled, rule.trigger_match, triggers_key)
        groups.setdefault(key, []).append(rule)

    result = []
    for (base_desc, enabled, trigger_match, _), group_rules in groups.items():
        actions = []
        for r in group_rules:
            for a in r.actions:
                actions.append(a.to_config_dict())
        triggers = [t.to_config_dict() for t in group_rules[0].triggers]
        config_rule = {
            "description": base_desc,
            "enabled": enabled,
            "trigger_match": trigger_match,
            "triggers": triggers,
            "actions": actions,
        }
        result.append(config_rule)
    return result


class EdgeRulesManager:
    """Manages Edge Rules on bunny.net Pull Zones."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def get_rules(self, zone_id: int) -> list[EdgeRule]:
        """Get all edge rules for a Pull Zone."""
        response = self.client.get(f"/pullzone/{zone_id}")
        rules_data = response.get("EdgeRules", []) if response else []
        return [EdgeRule.from_api_response(r) for r in rules_data]

    def export_rules(self, zone_id: int) -> list[dict]:
        """Export edge rules for a Pull Zone as config dicts."""
        rules = self.get_rules(zone_id)
        return group_api_rules_to_config(rules)

    def add_or_update_rule(self, zone_id: int, rule: EdgeRule) -> dict:
        """Add or update an edge rule."""
        payload = rule.to_api_payload()
        return self.client.post(f"/pullzone/{zone_id}/edgerules/addOrUpdate", payload)

    def delete_rule(self, zone_id: int, rule_guid: str) -> None:
        """Delete an edge rule by GUID."""
        self.client.delete(f"/pullzone/{zone_id}/edgerules/{rule_guid}")

    def delete_all_rules(self, zone_id: int) -> None:
        """Delete all edge rules for a Pull Zone."""
        rules = self.get_rules(zone_id)
        for rule in rules:
            if rule.guid:
                self.delete_rule(zone_id, rule.guid)

    def sync_rules(
        self,
        zone_id: int,
        rule_configs: list[dict],
        dry_run: bool = False,
    ) -> dict:
        """
        Sync edge rules to match desired configuration.

        This replaces all existing rules with the ones from config.

        Args:
            zone_id: Pull Zone ID
            rule_configs: List of rule configuration dicts
            dry_run: If True, only report changes without making them

        Returns:
            Dict with changes made
        """
        result = {
            "deleted": [],
            "created": [],
            "changes": [],
        }

        # Get current rules
        current_rules = self.get_rules(zone_id)

        # Parse desired rules from config
        desired_rules = []
        for config in rule_configs:
            desired_rules.extend(parse_rule_from_config(config))

        # Strategy: Delete all existing, create all from config
        # This is simpler than trying to diff by GUID since config doesn't have GUIDs

        # Delete existing rules
        for rule in current_rules:
            result["deleted"].append(rule.description)
            result["changes"].append(f"Deleting rule: {rule.description}")
            if not dry_run and rule.guid:
                self.delete_rule(zone_id, rule.guid)

        # Create new rules
        for rule in desired_rules:
            result["created"].append(rule.description)
            result["changes"].append(f"Creating rule: {rule.description}")
            if not dry_run:
                self.add_or_update_rule(zone_id, rule)

        return result
