# FastSSV Plugin Architecture

## Overview

FastSSV uses a **plugin-based rule system** where validation rules are automatically discovered and registered at import time. This architecture provides:

- **Extensibility**: Add new rules without modifying core code
- **Modularity**: Each rule is independent and self-contained
- **Flexibility**: Enable/disable rules by category or ID
- **Maintainability**: Clear separation of concerns

## Core Components

### 1. Rule Base Class (`core/base.py`)

All validation rules inherit from the abstract `Rule` class:

```python
from abc import ABC, abstractmethod

class Rule(ABC):
    """Abstract base class for validation rules."""

    def __init__(self):
        self.rule_id = ""
        self.category = ""
        self.description = ""

    @abstractmethod
    def validate(self, sql: str, dialect: str = "postgres") -> list[RuleViolation]:
        """Validate SQL query and return violations."""
        pass
```

### 2. RuleViolation Data Class

Violations are returned as structured objects:

```python
from dataclasses import dataclass
from enum import Enum

class Severity(str, Enum):
    ERROR = "ERROR"      # Blocks validation
    WARNING = "WARNING"  # Informational only

@dataclass
class RuleViolation:
    rule_id: str          # e.g., "semantic.standard_concept_enforcement"
    message: str          # Human-readable error message
    severity: Severity    # ERROR or WARNING
    location: str = ""    # Optional: location info

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "severity": self.severity.value,
            "location": self.location,
        }
```

### 3. Registry System (`core/registry.py`)

The registry manages rule discovery and access:

```python
from typing import Type

# Global registry
_rules: dict[str, Type[Rule]] = {}
_categories: dict[str, list[Type[Rule]]] = {}

def register(rule_id: str, category: str, description: str):
    """Decorator to register a rule class."""
    def decorator(cls: Type[Rule]) -> Type[Rule]:
        cls._rule_id = rule_id
        cls._category = category
        cls._description = description

        _rules[rule_id] = cls

        if category not in _categories:
            _categories[category] = []
        _categories[category].append(cls)

        return cls
    return decorator

def get_rule(rule_id: str) -> Type[Rule]:
    """Get a rule class by ID."""
    return _rules[rule_id]

def get_rules_by_category(category: str) -> list[Type[Rule]]:
    """Get all rules in a category."""
    return _categories.get(category, [])

def get_all_rules() -> list[Type[Rule]]:
    """Get all registered rules."""
    return list(_rules.values())
```

## Creating a New Rule

### Step 1: Create Rule File

Create a new Python file in the appropriate category directory:

```
src/foem/rules/
├── semantic/
│   └── my_new_rule.py    # For semantic rules
└── vocabulary/
    └── my_new_rule.py    # For vocabulary rules
```

### Step 2: Implement the Rule Class

```python
# src/foem/rules/semantic/my_new_rule.py

from fastssv.core.base import Rule, RuleViolation, Severity
from fastssv.core.registry import register
from fastssv.core.helpers import parse_sql

@register(
    rule_id="semantic.my_new_rule",
    category="semantic",
    description="Brief description of what this rule checks"
)
class MyNewRule(Rule):
    """
    Detailed documentation of the rule.

    Explains:
    - What OMOP CDM constraint this validates
    - Why this constraint matters
    - Examples of violations
    - How to fix violations
    """

    def validate(self, sql: str, dialect: str = "postgres") -> list[RuleViolation]:
        """
        Validate SQL query against this rule.

        Args:
            sql: SQL query string to validate
            dialect: SQL dialect (postgres, mysql, duckdb, etc.)

        Returns:
            List of RuleViolation objects. Empty list means no violations.
        """
        violations = []

        # Parse SQL into AST
        trees, parse_error = parse_sql(sql, dialect)
        if parse_error:
            # Skip validation if SQL doesn't parse
            return violations

        # Validation logic here
        if self._detect_violation(trees[0]):
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    message="Clear explanation of what went wrong and how to fix it",
                    severity=Severity.ERROR,  # or Severity.WARNING
                    location="optional: table.column or line number"
                )
            )

        return violations

    def _detect_violation(self, tree) -> bool:
        """Helper method for violation detection logic."""
        # Implementation details
        return False
```

### Step 3: Register the Rule

Import the rule in the category's `__init__.py`:

```python
# src/foem/rules/semantic/__init__.py

from . import join_path
from . import standard_concept
from . import maps_to_direction
from . import unmapped_concept
from . import my_new_rule  # Add this line
```

### Step 4: Add Tests

Create a test file:

```python
# tests/test_my_new_rule.py

import unittest
from fastssv.rules.semantic.my_new_rule import MyNewRule

class TestMyNewRule(unittest.TestCase):

    def setUp(self):
        self.rule = MyNewRule()

    def test_valid_query_passes(self):
        sql = "SELECT * FROM person"
        violations = self.rule.validate(sql)
        self.assertEqual(len(violations), 0)

    def test_invalid_query_fails(self):
        sql = "SELECT * FROM invalid_table"
        violations = self.rule.validate(sql)
        self.assertGreater(len(violations), 0)
        self.assertEqual(violations[0].rule_id, "semantic.my_new_rule")
```

## Using Rules

### Command Line Interface

```bash
# Run all rules (default)
python main.py query.sql

# Run specific category
python main.py query.sql --categories semantic

# Run multiple categories
python main.py query.sql --categories semantic vocabulary

# Run specific rule
python main.py query.sql --rules semantic.my_new_rule

# Run multiple specific rules
python main.py query.sql --rules semantic.join_path_validation semantic.standard_concept_enforcement
```

### Python API

```python
from fastssv import validate_sql_structured

# Run all rules
violations = validate_sql_structured(sql)

# Run specific category
violations = validate_sql_structured(sql, categories=["semantic"])

# Run specific rules
violations = validate_sql_structured(
    sql,
    rule_ids=["semantic.my_new_rule", "vocabulary.concept_string_filter"]
)

# Process violations
for v in violations:
    print(f"{v.severity}: [{v.rule_id}] {v.message}")
```

## Rule Categories

### Semantic Rules (`semantic`)

Rules that validate OMOP CDM schema and concept usage:

- `semantic.join_path_validation` - Table join validation
- `semantic.standard_concept_enforcement` - Standard concept enforcement
- `semantic.maps_to_direction` - Relationship direction validation
- `semantic.unmapped_concept_detection` - Unmapped concept detection

### Vocabulary Rules (`vocabulary`)

Rules that validate OMOP vocabulary lookup patterns:

- `vocabulary.no_string_concept_id` - String concept ID detection
- `vocabulary.concept_string_filter` - Concept table filtering

### Adding New Categories

To add a new category:

1. Create directory: `src/foem/rules/new_category/`
2. Add `__init__.py`
3. Add rule files
4. Import in `src/foem/rules/__init__.py`:
   ```python
   from . import semantic, vocabulary, new_category
   ```

## Best Practices

### Rule Implementation

1. **Single Responsibility**: Each rule should check one specific constraint
2. **Clear Messages**: Violation messages should explain what's wrong AND how to fix it
3. **Graceful Degradation**: Handle parse errors gracefully
4. **Performance**: Cache expensive operations when possible
5. **Testing**: Write comprehensive tests for valid and invalid cases

### Violation Messages

Good violation messages follow this pattern:

```
[What's wrong] + [Why it matters] + [How to fix it]

Example:
"Query uses STANDARD concept field 'drug_concept_id' without enforcing
standard_concept = 'S'. This may include non-standard concepts in results.

To fix, add: WHERE concept.standard_concept = 'S'"
```

### Severity Guidelines

Use **ERROR** for:
- Schema violations (invalid joins, missing tables)
- Semantic violations (wrong concept usage)
- Logic errors that will produce incorrect results

Use **WARNING** for:
- Style issues (inefficient patterns)
- Best practice recommendations
- Potential performance issues

## Helper Utilities

### SQL Parsing (`core/helpers.py`)

```python
from fastssv.core.helpers import parse_sql

# Parse SQL into sqlglot AST
trees, parse_error = parse_sql(sql, dialect="postgres")

if parse_error:
    # Handle parse error
    return []

# Work with AST
tree = trees[0]
```

### Common Patterns

Extract tables:
```python
from sqlglot import exp

tables = [
    table.name
    for table in tree.find_all(exp.Table)
]
```

Extract joins:
```python
joins = list(tree.find_all(exp.Join))
for join in joins:
    # Process join
    pass
```

Extract WHERE conditions:
```python
where = tree.find(exp.Where)
if where:
    # Process WHERE clause
    pass
```

## Architecture Benefits

1. **Zero Configuration**: Rules are auto-discovered
2. **Easy Extension**: Add rules without touching core code
3. **Selective Execution**: Run only needed rules
4. **Clean Separation**: Each rule is independent
5. **Testability**: Rules can be tested in isolation
6. **Maintainability**: Changes to one rule don't affect others

## Migration from Legacy System

The old validator function pattern:

```python
# OLD (deprecated)
def validate_join(sql, dialect):
    errors = []
    # validation logic
    return errors
```

Is replaced by:

```python
# NEW (current)
@register(rule_id="semantic.join_path_validation", category="semantic", description="...")
class JoinPathRule(Rule):
    def validate(self, sql, dialect):
        violations = []
        # validation logic
        return violations
```

Legacy functions still work for backward compatibility but are deprecated.

## Summary

The plugin architecture makes FastSSV:
- **Extensible**: Easy to add new rules
- **Flexible**: Granular control over which rules run
- **Maintainable**: Clear structure and separation
- **Testable**: Each rule can be tested independently

To add a new rule, simply:
1. Create a rule class with `@register`
2. Import it in `__init__.py`
3. Add tests

That's it! The rule is automatically available throughout the system.
