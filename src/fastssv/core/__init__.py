"""FastSSV core module - Base classes and registry for plugin-based rules."""

from .base import Rule, RuleViolation, Severity
from .registry import get_all_rules, get_rule, get_rules_by_category, register

__all__ = [
    "Rule",
    "RuleViolation",
    "Severity",
    "register",
    "get_all_rules",
    "get_rule",
    "get_rules_by_category",
]
