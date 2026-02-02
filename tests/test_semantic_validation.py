"""Unit tests for semantic validation."""

import unittest

from fastssv.rules import validate_omop_semantic_rules
from fastssv.core.registry import get_rules_by_category


def validate_standard_concept_mapping(sql: str, dialect: str = "postgres") -> list[str]:
    """Run only the standard concept enforcement rule."""
    from fastssv.core.base import Severity
    from fastssv.core.registry import get_rule

    rule = get_rule("semantic.standard_concept_enforcement")()
    violations = rule.validate(sql, dialect)

    # Also run join_path and maps_to_direction for warnings
    join_rule = get_rule("semantic.join_path_validation")()
    violations.extend(join_rule.validate(sql, dialect))

    maps_rule = get_rule("semantic.maps_to_direction")()
    violations.extend(maps_rule.validate(sql, dialect))

    # Convert to legacy string format
    results = []
    for v in violations:
        prefix = "Warning: " if v.severity == Severity.WARNING else ""
        results.append(f"{prefix}OMOP Semantic Rule Violation: {v.message}")

    return results


def validate_unmapped_concept_handling(sql: str, dialect: str = "postgres") -> list[str]:
    """Run only the unmapped concept handling rule."""
    from fastssv.core.base import Severity
    from fastssv.core.registry import get_rule

    rule = get_rule("semantic.unmapped_concept_handling")()
    violations = rule.validate(sql, dialect)

    # Convert to legacy string format
    results = []
    for v in violations:
        prefix = "Warning: " if v.severity == Severity.WARNING else ""
        results.append(f"{prefix}{v.message}")

    return results


class StandardConceptMappingTests(unittest.TestCase):
    """Tests for standard concept mapping rule."""

    def test_query_with_standard_concept_enforcement(self) -> None:
        """Query with standard_concept = 'S' should pass."""
        sql = """
        SELECT co.condition_concept_id
        FROM condition_occurrence co
        JOIN concept c ON co.condition_concept_id = c.concept_id
        WHERE c.standard_concept = 'S'
        """
        errors = validate_standard_concept_mapping(sql)
        self.assertEqual(errors, [])

    def test_query_with_maps_to_relationship(self) -> None:
        """Query with 'Maps to' relationship should pass."""
        sql = """
        SELECT co.condition_concept_id
        FROM condition_occurrence co
        JOIN concept_relationship cr ON co.condition_source_concept_id = cr.concept_id_1
        WHERE cr.relationship_id = 'Maps to'
        """
        errors = validate_standard_concept_mapping(sql)
        # Should pass (uses Maps to) but may have warnings about join path
        main_errors = [e for e in errors if not e.startswith("Warning:")]
        self.assertEqual(main_errors, [])

    def test_query_without_standard_enforcement(self) -> None:
        """Query using standard fields without enforcement should fail."""
        sql = """
        SELECT co.condition_concept_id
        FROM condition_occurrence co
        """
        errors = validate_standard_concept_mapping(sql)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("STANDARD concept fields" in e for e in errors))

    def test_query_with_standard_concept_in_join_on(self) -> None:
        """Query with standard_concept = 'S' in JOIN ON should pass."""
        sql = """
        SELECT co.condition_concept_id
        FROM condition_occurrence co
        JOIN concept c ON co.condition_concept_id = c.concept_id
            AND c.standard_concept = 'S'
        """
        errors = validate_standard_concept_mapping(sql)
        self.assertEqual(errors, [])

    def test_query_with_in_clause(self) -> None:
        """Query with standard_concept IN ('S') should pass."""
        sql = """
        SELECT co.condition_concept_id
        FROM condition_occurrence co
        JOIN concept c ON co.condition_concept_id = c.concept_id
        WHERE c.standard_concept IN ('S')
        """
        errors = validate_standard_concept_mapping(sql)
        self.assertEqual(errors, [])


class UnmappedConceptHandlingTests(unittest.TestCase):
    """Tests for concept_id = 0 handling rule."""

    def test_specific_concept_id_without_zero_handling(self) -> None:
        """Query with specific concept_id but no 0 handling should warn."""
        sql = """
        SELECT * FROM condition_occurrence
        WHERE condition_concept_id = 201826
        """
        warnings = validate_unmapped_concept_handling(sql)
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("concept_id = 0" in w for w in warnings))

    def test_concept_id_with_greater_than_zero(self) -> None:
        """Query with > 0 should not warn."""
        sql = """
        SELECT * FROM condition_occurrence
        WHERE condition_concept_id = 201826 AND condition_concept_id > 0
        """
        warnings = validate_unmapped_concept_handling(sql)
        self.assertEqual(warnings, [])

    def test_concept_id_with_not_equal_zero(self) -> None:
        """Query with != 0 should not warn."""
        sql = """
        SELECT * FROM condition_occurrence
        WHERE condition_concept_id = 201826 AND condition_concept_id != 0
        """
        warnings = validate_unmapped_concept_handling(sql)
        self.assertEqual(warnings, [])

    def test_in_clause_without_zero_handling(self) -> None:
        """Query with IN clause but no 0 handling should warn."""
        sql = """
        SELECT * FROM condition_occurrence
        WHERE condition_concept_id IN (201826, 201820)
        """
        warnings = validate_unmapped_concept_handling(sql)
        self.assertTrue(len(warnings) > 0)

    def test_no_specific_filter(self) -> None:
        """Query without specific concept_id filter should not warn."""
        sql = """
        SELECT co.* FROM condition_occurrence co
        JOIN concept c ON co.condition_concept_id = c.concept_id
        """
        warnings = validate_unmapped_concept_handling(sql)
        self.assertEqual(warnings, [])

    def test_non_clinical_table(self) -> None:
        """Query on concept table should not warn."""
        sql = """
        SELECT * FROM concept
        WHERE concept_id = 201826
        """
        warnings = validate_unmapped_concept_handling(sql)
        self.assertEqual(warnings, [])


class CombinedSemanticValidationTests(unittest.TestCase):
    """Tests for combined semantic validation."""

    def test_valid_query(self) -> None:
        """A properly constructed query should pass all validations."""
        sql = """
        SELECT co.condition_concept_id, c.concept_name
        FROM condition_occurrence co
        JOIN concept_ancestor ca ON co.condition_concept_id = ca.descendant_concept_id
        JOIN concept c ON co.condition_concept_id = c.concept_id
        WHERE ca.ancestor_concept_id = 201826
        AND co.condition_concept_id > 0
        AND c.standard_concept = 'S'
        """
        errors = validate_omop_semantic_rules(sql)
        self.assertEqual(errors, [])

    def test_invalid_sql(self) -> None:
        """Invalid SQL should return parse error."""
        sql = "SELECT FROM WHERE"
        errors = validate_omop_semantic_rules(sql)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("parse error" in e.lower() or "error" in e.lower() for e in errors))


class HierarchyExpansionTests(unittest.TestCase):
    """Tests for hierarchy expansion rule (concept_ancestor requirement)."""

    def _validate_hierarchy(self, sql: str, dialect: str = "postgres") -> list[str]:
        """Run only the hierarchy expansion rule."""
        from fastssv.core.base import Severity
        from fastssv.core.registry import get_rule

        rule = get_rule("semantic.hierarchy_expansion_required")()
        violations = rule.validate(sql, dialect)

        results = []
        for v in violations:
            prefix = "Warning: " if v.severity == Severity.WARNING else ""
            results.append(f"{prefix}{v.message}")
        return results

    def test_drug_filter_without_ancestor_should_error(self) -> None:
        """Filtering drug_concept_id without concept_ancestor should error."""
        sql = """
        SELECT * FROM drug_exposure
        WHERE drug_concept_id = 1234567
        """
        errors = self._validate_hierarchy(sql)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("concept_ancestor" in e for e in errors))
        self.assertTrue(any("drug_exposure.drug_concept_id" in e for e in errors))

    def test_condition_filter_without_ancestor_should_error(self) -> None:
        """Filtering condition_concept_id without concept_ancestor should error."""
        sql = """
        SELECT * FROM condition_occurrence
        WHERE condition_concept_id = 201826
        """
        errors = self._validate_hierarchy(sql)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("concept_ancestor" in e for e in errors))
        self.assertTrue(any("condition_occurrence.condition_concept_id" in e for e in errors))

    def test_in_clause_without_ancestor_should_error(self) -> None:
        """IN clause on drug_concept_id without concept_ancestor should error."""
        sql = """
        SELECT * FROM drug_exposure
        WHERE drug_concept_id IN (1234, 5678, 9012)
        """
        errors = self._validate_hierarchy(sql)
        self.assertTrue(len(errors) > 0)

    def test_with_concept_ancestor_should_pass(self) -> None:
        """Query using concept_ancestor for hierarchy should pass."""
        sql = """
        SELECT de.*
        FROM drug_exposure de
        JOIN concept_ancestor ca ON de.drug_concept_id = ca.descendant_concept_id
        WHERE ca.ancestor_concept_id = 1234567
        """
        errors = self._validate_hierarchy(sql)
        # Should pass (uses concept_ancestor)
        main_errors = [e for e in errors if not e.startswith("Warning:")]
        self.assertEqual(main_errors, [])

    def test_with_concept_ancestor_cte_should_pass(self) -> None:
        """Query using concept_ancestor via CTE should pass."""
        sql = """
        WITH drug_hierarchy AS (
            SELECT descendant_concept_id AS concept_id
            FROM concept_ancestor
            WHERE ancestor_concept_id = 1234567
        )
        SELECT de.*
        FROM drug_exposure de
        JOIN drug_hierarchy dh ON de.drug_concept_id = dh.concept_id
        """
        errors = self._validate_hierarchy(sql)
        main_errors = [e for e in errors if not e.startswith("Warning:")]
        self.assertEqual(main_errors, [])

    def test_zero_concept_id_should_be_exempt(self) -> None:
        """Filtering on concept_id = 0 should not trigger the rule."""
        sql = """
        SELECT * FROM drug_exposure
        WHERE drug_concept_id = 0
        """
        errors = self._validate_hierarchy(sql)
        self.assertEqual(errors, [])

    def test_no_filter_should_not_trigger(self) -> None:
        """Query without filtering on drug/condition concept_id should not trigger."""
        sql = """
        SELECT drug_concept_id, person_id
        FROM drug_exposure
        WHERE person_id = 12345
        """
        errors = self._validate_hierarchy(sql)
        self.assertEqual(errors, [])

    def test_other_concept_columns_should_not_trigger(self) -> None:
        """Filtering on other concept_id columns should not trigger."""
        sql = """
        SELECT * FROM measurement
        WHERE measurement_concept_id = 3012345
        """
        errors = self._validate_hierarchy(sql)
        self.assertEqual(errors, [])

    def test_wrong_join_direction_should_warn(self) -> None:
        """Joining on ancestor_concept_id instead of descendant should warn."""
        # This query filters on drug_concept_id AND uses concept_ancestor,
        # but joins in the wrong direction (ancestor_concept_id instead of descendant)
        sql = """
        SELECT de.*
        FROM drug_exposure de
        JOIN concept_ancestor ca ON de.drug_concept_id = ca.ancestor_concept_id
        WHERE de.drug_concept_id = 1234567
        """
        errors = self._validate_hierarchy(sql)
        # Should have a warning about join direction
        warnings = [e for e in errors if e.startswith("Warning:")]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("direction" in w.lower() for w in warnings))


class EdgeCasesTests(unittest.TestCase):
    """Edge cases for semantic validation."""

    def test_cte_query(self) -> None:
        """Query with CTE should be handled correctly."""
        sql = """
        WITH diabetic_patients AS (
            SELECT co.person_id, co.condition_concept_id
            FROM condition_occurrence co
            JOIN concept_ancestor ca ON co.condition_concept_id = ca.descendant_concept_id
            WHERE ca.ancestor_concept_id = 201826
            AND co.condition_concept_id > 0
        )
        SELECT dp.*, c.concept_name
        FROM diabetic_patients dp
        JOIN concept c ON dp.condition_concept_id = c.concept_id
        WHERE c.standard_concept = 'S'
        """
        errors = validate_omop_semantic_rules(sql)
        # May have warnings but shouldn't have main errors
        main_errors = [e for e in errors if "Violation" in e]
        self.assertEqual(main_errors, [])

    def test_multiple_clinical_tables(self) -> None:
        """Query joining multiple clinical tables."""
        sql = """
        SELECT co.condition_concept_id, de.drug_concept_id
        FROM condition_occurrence co
        JOIN drug_exposure de ON co.person_id = de.person_id
        JOIN concept c1 ON co.condition_concept_id = c1.concept_id
        JOIN concept c2 ON de.drug_concept_id = c2.concept_id
        WHERE c1.standard_concept = 'S'
        AND c2.standard_concept = 'S'
        """
        errors = validate_standard_concept_mapping(sql)
        self.assertEqual(errors, [])

    def test_subquery(self) -> None:
        """Query with subquery should be handled."""
        sql = """
        SELECT * FROM condition_occurrence
        WHERE condition_concept_id IN (
            SELECT concept_id FROM concept
            WHERE vocabulary_id = 'SNOMED' AND standard_concept = 'S'
        )
        """
        errors = validate_standard_concept_mapping(sql)
        # The subquery has standard_concept = 'S', so this should pass
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
