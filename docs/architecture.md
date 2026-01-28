# FastSSV Architecture

## Directory Structure

```
src/foem/
├── __init__.py                 # Main API: validate_sql(), validate_sql_structured()
├── core/
│   ├── __init__.py
│   ├── base.py                 # Rule base class, RuleViolation, Severity
│   ├── registry.py             # Plugin registry with @register decorator
│   └── helpers.py              # SQL parsing utilities
├── rules/
│   ├── __init__.py             # Legacy validator functions
│   ├── semantic/
│   │   ├── __init__.py
│   │   ├── join_path.py        # Join path validation rule
│   │   ├── standard_concept.py # Standard concept enforcement rule
│   │   ├── maps_to_direction.py # Maps-to relationship direction rule
│   │   └── unmapped_concept.py # Unmapped concept detection rule
│   ├── vocabulary/
│   │   ├── __init__.py
│   │   ├── no_string_id.py     # String ID lookup detection rule
│   │   └── concept_lookup.py   # Concept table string filter rule
│   ├── semantic_rules.py       # Deprecated: legacy semantic validators
│   └── vocabulary_rules.py     # Deprecated: legacy vocabulary validators
└── schemas/
    ├── __init__.py
    ├── cdm_schema.py            # OMOP CDM schema definition
    └── semantic_schema.py       # Vocabulary rules (STANDARD vs SOURCE)
```

## Architecture Overview

FastSSV uses a **plugin-based architecture** where validation rules are automatically discovered and registered at import time.

### Separation of Concerns

1. **Core** (`core/`)
   - `base.py`: Abstract `Rule` base class, `RuleViolation`, and `Severity` enum
   - `registry.py`: Plugin registry with `@register` decorator for automatic rule discovery
   - `helpers.py`: SQL parsing utilities (sqlglot-based)

2. **Schemas** (`schemas/`)
   - Pure data definitions
   - CDM table relationships
   - Vocabulary field classifications
   - No validation logic

3. **Rules** (`rules/`)
   - Each rule is a class inheriting from `Rule`
   - Registered automatically via `@register` decorator
   - Organized by category (semantic, vocabulary)
   - Returns list of `RuleViolation` objects

4. **Main API** (`__init__.py`)
   - Unified interface: `validate_sql()` (legacy) and `validate_sql_structured()` (recommended)
   - Coordinates multiple rules via registry
   - Supports filtering by rule ID or category
   - Maintains backward compatibility

## Rule Interface

Each rule follows this pattern:

```python
from fastssv.core.base import Rule, RuleViolation, Severity
from fastssv.core.registry import register

@register(rule_id="category.rule_name", category="category", description="Rule description")
class MyRule(Rule):
    """Validation rule for specific OMOP CDM constraint."""

    def validate(self, sql: str, dialect: str = "postgres") -> list[RuleViolation]:
        """
        Args:
            sql: SQL query to validate
            dialect: SQL dialect for parsing

        Returns:
            List of RuleViolation objects (empty if valid)
        """
        violations = []

        # Validation logic here
        if violation_detected:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    message="Description of violation",
                    severity=Severity.ERROR,  # or Severity.WARNING
                    location="optional location info"
                )
            )

        return violations
```

### RuleViolation Structure

```python
@dataclass
class RuleViolation:
    rule_id: str          # e.g., "semantic.standard_concept_enforcement"
    message: str          # Human-readable error message
    severity: Severity    # ERROR or WARNING
    location: str = ""    # Optional: file, line, or SQL fragment

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
```

## Adding New Rules

To add a new validation rule:

1. Create a new rule file in the appropriate category directory:
   - For semantic rules: `src/foem/rules/semantic/my_rule.py`
   - For vocabulary rules: `src/foem/rules/vocabulary/my_rule.py`
   - For a new category: `src/foem/rules/new_category/my_rule.py`

2. Implement the rule class:
   ```python
   from fastssv.core.base import Rule, RuleViolation, Severity
   from fastssv.core.registry import register

   @register(
       rule_id="category.my_rule",
       category="category",
       description="Brief description of what this rule checks"
   )
   class MyRule(Rule):
       """Detailed documentation of the rule."""

       def validate(self, sql: str, dialect: str = "postgres") -> list[RuleViolation]:
           violations = []
           # Validation logic here
           return violations
   ```

3. Import in the category's `__init__.py`:
   ```python
   # In src/foem/rules/category/__init__.py
   from . import my_rule  # This triggers registration
   ```

4. Add tests in `tests/test_my_rule.py`

**That's it!** The rule is automatically discovered and available via:
- `validate_sql_structured(sql, categories=["category"])`
- `validate_sql_structured(sql, rule_ids=["category.my_rule"])`
- CLI: `python main.py query.sql --categories category`
- CLI: `python main.py query.sql --rules category.my_rule`

## Current Rules

### Semantic Rules (Category: `semantic`)

1. **join_path** (`semantic.join_path_validation`)
   - Validates table joins against OMOP CDM schema
   - Checks join predicates using sqlglot AST
   - Verifies foreign key → primary key relationships

2. **standard_concept** (`semantic.standard_concept_enforcement`)
   - Ensures STANDARD concept fields enforce `standard_concept = 'S'`
   - Validates use of 'Maps to' relationships
   - Detects missing standard concept enforcement

3. **maps_to_direction** (`semantic.maps_to_direction`)
   - Validates concept_relationship 'Maps to' direction
   - Ensures proper source → standard mapping

4. **unmapped_concept** (`semantic.unmapped_concept_detection`)
   - Detects use of unmapped (concept_id = 0) concepts

### Vocabulary Rules (Category: `vocabulary`)

1. **no_string_id** (`vocabulary.no_string_concept_id`)
   - Detects string lookups for concept IDs
   - Warns against `concept_name = 'text'` patterns

2. **concept_lookup** (`vocabulary.concept_string_filter`)
   - Validates proper use of concept table lookups
   - Encourages concept_id-based filtering

## Extension Points

The plugin architecture makes it easy to add new rules:

1. **Add vocabulary checks**: Detect actual vocabulary IDs in WHERE clauses
2. **Add concept hierarchy validation**: Check ancestor/descendant usage
3. **Add domain validation**: Ensure concepts match table domains
4. **Add temporal checks**: Validate date field usage

Simply create a new rule class with the `@register` decorator. No changes to the core architecture needed.

## Registry System

The registry (`core/registry.py`) provides:

- `@register(rule_id, category, description)`: Decorator to register rules
- `get_all_rules()`: Get all registered rule classes
- `get_rule(rule_id)`: Get specific rule by ID
- `get_rules_by_category(category)`: Get all rules in a category

Rules are automatically discovered at import time when their module is imported.
