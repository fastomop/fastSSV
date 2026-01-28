# Working with Semantic Rules

This guide explains how to work with and extend `semantic_rules.py`, which is now properly integrated into the FastSSV validation framework.

## Quick Start

### Using Semantic Validation

```python
from fastssv import validate_sql_structured  # Package name is 'foem' for backward compatibility

# Run all rules (recommended API)
violations = validate_sql_structured(sql_query)
for v in violations:
    print(f"{v.severity}: [{v.rule_id}] {v.message}")

# Run only semantic rules
violations = validate_sql_structured(sql_query, categories=["semantic"])

# Run specific rule
violations = validate_sql_structured(
    sql_query,
    rule_ids=["semantic.standard_concept_enforcement"]
)

# Legacy API (for backward compatibility)
from fastssv import validate_sql
results = validate_sql(sql_query, categories=["semantic"])
print(results["semantic_errors"])
```

### CLI Usage

```bash
# Run all rules (default)
python main.py query.sql

# Run only semantic rules
python main.py query.sql --categories semantic

# Run only vocabulary rules
python main.py query.sql --categories vocabulary

# Run both semantic and vocabulary
python main.py query.sql --categories semantic vocabulary

# Run specific rules
python main.py query.sql --rules semantic.standard_concept_enforcement
```

## Understanding Semantic Rules

The semantic validator checks OMOP vocabulary usage by classifying concept fields into two types:

### STANDARD Concept Fields

Fields that should contain **standard** concepts (SNOMED, RxNorm, LOINC, etc.):

```python
STANDARD_CONCEPT_FIELDS = {
    ("condition_occurrence", "condition_concept_id"),
    ("drug_exposure", "drug_concept_id"),
    ("drug_exposure", "route_concept_id"),
    ("procedure_occurrence", "procedure_concept_id"),
    ("measurement", "measurement_concept_id"),
    # ... and more
}
```

### SOURCE Concept Fields

Fields that can contain **source** vocabularies (ICD10CM, CPT4, NDC, etc.):

```python
SOURCE_CONCEPT_FIELDS = {
    ("condition_occurrence", "condition_source_concept_id"),
    ("drug_exposure", "drug_source_concept_id"),
    ("procedure_occurrence", "procedure_source_concept_id"),
    # ... and more
}
```

## Extending Semantic Validation

The plugin architecture makes adding new rules easy. Here are common use cases:

### 1. Add Vocabulary Detection Rule

Create a new rule to detect actual vocabulary usage:

```python
# In src/foem/rules/semantic/vocabulary_detection.py

from fastssv.core.base import Rule, RuleViolation, Severity
from fastssv.core.registry import register
from fastssv.core.helpers import parse_sql

@register(
    rule_id="semantic.vocabulary_detection",
    category="semantic",
    description="Validates vocabulary IDs in concept filters"
)
class VocabularyDetectionRule(Rule):
    """Detects and validates vocabulary usage in concept filters."""

    def validate(self, sql: str, dialect: str = "postgres") -> list[RuleViolation]:
        violations = []
        trees, parse_error = parse_sql(sql, dialect)
        if parse_error:
            return violations

        # Extract concept IDs from WHERE clauses
        concept_values = self._extract_concept_values(trees[0])

        for table, column, concept_id in concept_values:
            # TODO: Query OMOP vocabulary to check if concept_id
            # is from a standard vocabulary
            pass

        return violations

    def _extract_concept_values(self, tree):
        """Extract concept IDs used in WHERE clauses."""
        # Parse SQL and find patterns like: drug_concept_id = 1234
        # Return: [(table, column, concept_id), ...]
        return []
```

Then import in `src/foem/rules/semantic/__init__.py`:
```python
from . import vocabulary_detection
```

### 2. Add Domain Validation Rule

Check that concepts match expected domains:

```python
# In src/foem/rules/semantic/domain_validation.py

from fastssv.core.base import Rule, RuleViolation, Severity
from fastssv.core.registry import register

EXPECTED_DOMAINS = {
    ("drug_exposure", "drug_concept_id"): "Drug",
    ("condition_occurrence", "condition_concept_id"): "Condition",
    ("measurement", "measurement_concept_id"): "Measurement",
}

@register(
    rule_id="semantic.domain_validation",
    category="semantic",
    description="Validates concept domains match table expectations"
)
class DomainValidationRule(Rule):
    """Ensures concepts belong to the correct domain for their table."""

    def validate(self, sql: str, dialect: str = "postgres") -> list[RuleViolation]:
        violations = []

        # Extract concept references
        references = self._extract_concept_references(sql, dialect)

        for ref in references:
            expected_domain = EXPECTED_DOMAINS.get((ref.table, ref.column))
            if expected_domain:
                # TODO: Validate concept belongs to expected domain
                pass

        return violations
```

### 3. Add Ancestor/Descendant Validation Rule

Check proper use of concept hierarchies:

```python
# In src/foem/rules/semantic/hierarchy_validation.py

from fastssv.core.base import Rule, RuleViolation, Severity
from fastssv.core.registry import register

@register(
    rule_id="semantic.hierarchy_validation",
    category="semantic",
    description="Validates proper use of concept_ancestor relationships"
)
class HierarchyValidationRule(Rule):
    """Validates concept hierarchy usage."""

    def validate(self, sql: str, dialect: str = "postgres") -> list[RuleViolation]:
        violations = []

        # Find queries using concept_ancestor table
        hierarchy_patterns = self._extract_hierarchy_queries(sql, dialect)

        # Look for patterns like:
        # JOIN concept_ancestor ca ON de.drug_concept_id = ca.descendant_concept_id
        # WHERE ca.ancestor_concept_id = 1234

        return violations

    def _extract_hierarchy_queries(self, sql, dialect):
        """Find queries using concept_ancestor table."""
        return []
```

## Current Implementation Status

**Implemented:**
- Concept field extraction from SQL
- Classification of STANDARD vs SOURCE fields
- Table alias resolution
- Basic validation framework

**Ready for Extension:**
- Actual vocabulary checking (requires OMOP database connection)
- Domain validation
- Concept hierarchy validation
- Temporal validation

## File Locations

- **Schema definitions**: `src/foem/schemas/semantic_schema.py`
- **Rule implementations**: `src/foem/rules/semantic/`
  - `join_path.py` - Join path validation
  - `standard_concept.py` - Standard concept enforcement
  - `maps_to_direction.py` - Maps-to relationship validation
  - `unmapped_concept.py` - Unmapped concept detection
- **Tests**: `tests/test_semantic_validation.py`
- **Main API**: `src/foem/__init__.py`

## Adding New Semantic Rules

### Adding a New Concept Field Classification

To add a new concept field classification:

1. Edit `src/foem/schemas/semantic_schema.py`:
   ```python
   STANDARD_CONCEPT_FIELDS = {
       # ... existing fields ...
       ("new_table", "new_concept_id"),  # Add here
   }
   ```

2. Tests are automatically updated (they use the schema)

3. No changes needed to validation logic

### Adding a New Validation Rule

To add a completely new validation rule:

1. Create `src/foem/rules/semantic/my_new_rule.py`
2. Implement the rule with `@register` decorator
3. Import in `src/foem/rules/semantic/__init__.py`
4. Add tests in `tests/test_my_new_rule.py`

That's it! The rule is automatically available.

## Testing

Run semantic validation tests:

```bash
# All semantic tests
python -m unittest tests.test_semantic_validation -v

# Specific test
python -m unittest tests.test_semantic_validation.SemanticValidationTests.test_extract_concept_references_basic -v
```

## Next Steps

The semantic rule system provides a solid foundation. Recommended extensions:

1. **Connect to OMOP vocabulary database** to validate actual concept IDs
2. **Add vocabulary-specific rules** (e.g., RxNorm only for drugs)
3. **Implement domain checking** using OMOP concept.domain_id
4. **Add temporal validation** for date fields
5. **Create vocabulary fixture data** for testing without database

All extensions should be added as new rule classes in `src/foem/rules/semantic/` following the plugin pattern.
