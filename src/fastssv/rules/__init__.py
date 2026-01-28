"""FastSSV validation rules module.

This module auto-imports all rule submodules to trigger rule registration.
"""

# Import rule modules to trigger registration via @register decorator
from . import semantic, vocabulary

# For backward compatibility, also provide the legacy functions
from fastssv.core.base import RuleViolation, Severity
from fastssv.core.registry import get_all_rules, get_rule, get_rules_by_category


def validate_omop_semantic_rules(sql: str, dialect: str = "postgres") -> list[str]:
    """Legacy function for backward compatibility.

    Runs all semantic rules and returns list of error message strings.
    """
    from fastssv.core.helpers import parse_sql

    # Check for parse errors first (for backward compatibility)
    trees, parse_error = parse_sql(sql, dialect)
    if parse_error:
        return [parse_error]

    violations = []
    for rule_cls in get_rules_by_category("semantic"):
        rule = rule_cls()
        violations.extend(rule.validate(sql, dialect))

    # Convert to legacy string format
    results = []
    for v in violations:
        prefix = "Warning: " if v.severity == Severity.WARNING else ""
        results.append(f"{prefix}OMOP Semantic Rule Violation: {v.message}")

    return results


def validate_omop_vocabulary_rules(sql: str, dialect: str = "postgres") -> list[str]:
    """Legacy function for backward compatibility.

    Runs all vocabulary rules and returns list of error message strings.
    """
    from fastssv.core.helpers import parse_sql

    # Check for parse errors first (for backward compatibility)
    trees, parse_error = parse_sql(sql, dialect)
    if parse_error:
        return [parse_error]

    violations = []
    for rule_cls in get_rules_by_category("vocabulary"):
        rule = rule_cls()
        violations.extend(rule.validate(sql, dialect))

    # Convert to legacy string format
    results = []
    for v in violations:
        prefix = "Warning: " if v.severity == Severity.WARNING else ""
        results.append(f"{prefix}{v.message}")

    return results


__all__ = [
    # Rule modules
    "semantic",
    "vocabulary",
    # Legacy functions
    "validate_omop_semantic_rules",
    "validate_omop_vocabulary_rules",
    # Registry access
    "get_all_rules",
    "get_rule",
    "get_rules_by_category",
    # Base classes
    "RuleViolation",
    "Severity",
]
