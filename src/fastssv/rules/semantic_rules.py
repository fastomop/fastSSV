"""
Semantic validation for OMOP vocabulary usage in SQL queries.

Rules implemented:
1. Standard Concept Mapping: If query uses clinical STANDARD concept fields
   (e.g. condition_occurrence.condition_concept_id), then it must either:
    A) enforce standard concepts via concept.standard_concept = 'S'
    OR
    B) use concept_relationship relationship_id = 'Maps to'

2. Unmapped Concept Handling: When filtering by specific *_concept_id values,
   warn if concept_id = 0 (unmapped records) is not explicitly handled.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from ..schemas import STANDARD_CONCEPT_FIELDS, SOURCE_CONCEPT_FIELDS


# =========================
# 1) Configuration / Rules
# =========================

# relationship_id values commonly used for standard mapping in OMOP
MAPS_TO_RELATIONSHIP = "Maps to"


@dataclass
class SemanticValidationError:
    """Structured error for semantic validation failures."""
    rule: str
    message: str
    details: Optional[Dict] = None

    def __str__(self) -> str:
        return f"{self.rule}: {self.message}"


# =========================
# 2) Helpers
# =========================

def normalize_name(s: str) -> str:
    return s.lower().strip()


def _extract_aliases(tree: exp.Expression) -> Dict[str, str]:
    """
    Builds a mapping:
      alias -> real_table_name

    Example:
      FROM condition_occurrence c
    gives:
      {"c": "condition_occurrence", "condition_occurrence": "condition_occurrence"}

    Also handles CTEs by extracting their names.
    """
    aliases: Dict[str, str] = {}

    # Handle CTEs - extract CTE names as self-referencing aliases
    for cte in tree.find_all(exp.CTE):
        cte_alias = cte.alias
        if cte_alias:
            cte_name = normalize_name(cte_alias)
            aliases[cte_name] = cte_name

    for t in tree.find_all(exp.Table):
        real = normalize_name(t.name)

        # SQLGlot aliases are sometimes objects; alias_or_name is safe
        alias = t.alias_or_name
        if alias:
            alias_norm = normalize_name(alias)
            aliases[alias_norm] = real

        aliases[real] = real

    return aliases


def _is_string_literal(e: exp.Expression) -> bool:
    return isinstance(e, exp.Literal) and e.is_string


def _resolve_table_col(col: exp.Column, aliases: Dict[str, str]) -> Tuple[str, str]:
    """
    Resolve exp.Column into (real_table_name, column_name).

    Example:
      c.condition_concept_id -> ("condition_occurrence", "condition_concept_id")
    """
    col_name = normalize_name(col.name)
    table_name = ""
    if col.table:
        table_alias = normalize_name(col.table)
        table_name = aliases.get(table_alias, table_alias)
    return table_name, col_name


def _uses_table(tree: exp.Expression, table_name: str) -> bool:
    """True if query references a table by name anywhere."""
    target = normalize_name(table_name)
    return any(normalize_name(t.name) == target for t in tree.find_all(exp.Table))


def _is_in_where_or_join_clause(node: exp.Expression) -> bool:
    """Check if an expression node is within a WHERE clause or JOIN ON condition."""
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.Where):
            return True
        # Check if this is a JOIN's ON condition
        if isinstance(parent, exp.Join):
            # The node is part of the join's ON clause
            return True
        parent = parent.parent
    return False


def _check_equality_condition(
    tree: exp.Expression,
    column_name: str,
    expected_values: Set[str],
    require_where_clause: bool = True
) -> bool:
    """
    Check if there's an equality condition (col = 'value' or 'value' = col)
    for the given column with one of the expected values.

    Args:
        tree: The SQL AST
        column_name: The column to check (normalized)
        expected_values: Set of acceptable values (normalized)
        require_where_clause: If True, condition must be in WHERE/JOIN ON clause
    """
    for eq in tree.find_all(exp.EQ):
        if require_where_clause and not _is_in_where_or_join_clause(eq):
            continue

        left, right = eq.left, eq.right

        # column = 'value'
        if isinstance(left, exp.Column) and normalize_name(left.name) == column_name:
            if _is_string_literal(right) and normalize_name(right.this) in expected_values:
                return True

        # 'value' = column
        if isinstance(right, exp.Column) and normalize_name(right.name) == column_name:
            if _is_string_literal(left) and normalize_name(left.this) in expected_values:
                return True

    return False


def _check_in_condition(
    tree: exp.Expression,
    column_name: str,
    expected_values: Set[str],
    require_where_clause: bool = True
) -> bool:
    """
    Check if there's an IN condition (col IN ('value1', 'value2', ...))
    for the given column where at least one expected value is present.

    Args:
        tree: The SQL AST
        column_name: The column to check (normalized)
        expected_values: Set of acceptable values (normalized)
        require_where_clause: If True, condition must be in WHERE/JOIN ON clause
    """
    for in_expr in tree.find_all(exp.In):
        if require_where_clause and not _is_in_where_or_join_clause(in_expr):
            continue

        # Check if the column matches
        if not isinstance(in_expr.this, exp.Column):
            continue
        if normalize_name(in_expr.this.name) != column_name:
            continue

        # Check the values in the IN clause
        # in_expr.expressions contains the list items, or in_expr.query for subquery
        expressions = in_expr.expressions
        if expressions:
            for val_expr in expressions:
                if _is_string_literal(val_expr):
                    if normalize_name(val_expr.this) in expected_values:
                        return True

    return False


def _check_condition(
    tree: exp.Expression,
    column_name: str,
    expected_values: Set[str],
    require_where_clause: bool = True
) -> bool:
    """
    Check if there's a condition (equality or IN) for the given column
    with one of the expected values.
    """
    return (
        _check_equality_condition(tree, column_name, expected_values, require_where_clause) or
        _check_in_condition(tree, column_name, expected_values, require_where_clause)
    )


def _enforces_standard_concept(tree: exp.Expression) -> bool:
    """
    Detects whether query enforces standard concepts via:
      concept.standard_concept = 'S'
      or
      standard_concept IN ('S')

    The condition must be in a WHERE clause or JOIN ON clause.
    """
    if not _uses_table(tree, "concept"):
        return False

    return _check_condition(tree, "standard_concept", {"s"}, require_where_clause=True)


def _uses_maps_to_relationship(tree: exp.Expression) -> bool:
    """
    Detects whether query uses concept_relationship relationship_id = 'Maps to'.
    The condition must be in a WHERE clause or JOIN ON clause.
    """
    if not _uses_table(tree, "concept_relationship"):
        return False

    return _check_condition(
        tree,
        "relationship_id",
        {normalize_name(MAPS_TO_RELATIONSHIP)},
        require_where_clause=True
    )


def _extract_concept_references(
    tree: exp.Expression, aliases: Dict[str, str]
) -> List[Tuple[str, str]]:
    """
    Extracts all resolved (table, column) references where column looks like a concept field:
      - *_concept_id
      - concept_id
    """
    refs: List[Tuple[str, str]] = []

    for col in tree.find_all(exp.Column):
        table, col_name = _resolve_table_col(col, aliases)

        if not table:
            continue

        if col_name == "concept_id" or col_name.endswith("_concept_id"):
            refs.append((table, col_name))

    return refs


def _extract_join_conditions(tree: exp.Expression, aliases: Dict[str, str]) -> List[Tuple[str, str, str, str]]:
    """
    Extract JOIN conditions to verify proper table linking.

    Returns list of tuples: (left_table, left_col, right_table, right_col)
    """
    join_conditions: List[Tuple[str, str, str, str]] = []

    for eq in tree.find_all(exp.EQ):
        # Check if this is in a JOIN context
        parent = eq.parent
        in_join = False
        while parent:
            if isinstance(parent, exp.Join):
                in_join = True
                break
            parent = parent.parent

        if not in_join:
            continue

        left, right = eq.left, eq.right

        if isinstance(left, exp.Column) and isinstance(right, exp.Column):
            left_table, left_col = _resolve_table_col(left, aliases)
            right_table, right_col = _resolve_table_col(right, aliases)

            if left_table and right_table:
                join_conditions.append((left_table, left_col, right_table, right_col))

    return join_conditions


def _verify_concept_join_path(
    tree: exp.Expression,
    aliases: Dict[str, str],
    used_standard_fields: Set[Tuple[str, str]]
) -> Tuple[bool, List[str]]:
    """
    Verify that concept or concept_relationship tables are properly joined
    to the clinical tables using the standard concept fields.

    Returns (is_valid, list_of_warnings)
    """
    warnings: List[str] = []

    uses_concept = _uses_table(tree, "concept")
    uses_concept_rel = _uses_table(tree, "concept_relationship")

    if not uses_concept and not uses_concept_rel:
        return True, []  # No vocabulary tables used, nothing to verify

    join_conditions = _extract_join_conditions(tree, aliases)

    # Build a set of all join connections
    join_pairs: Set[Tuple[str, str, str, str]] = set(join_conditions)
    # Add reverse pairs for bidirectional lookup
    for lt, lc, rt, rc in join_conditions:
        join_pairs.add((rt, rc, lt, lc))

    linked_to_concept = False
    linked_to_concept_rel = False

    for table, col in used_standard_fields:
        # Check for join to concept table
        for lt, lc, rt, rc in join_pairs:
            if lt == table and lc == col:
                if rt == "concept" and rc == "concept_id":
                    linked_to_concept = True
                if rt == "concept_relationship":
                    linked_to_concept_rel = True

    if uses_concept and not linked_to_concept:
        warnings.append(
            f"Warning: Query uses 'concept' table but it may not be properly joined "
            f"to the clinical tables via standard concept fields."
        )

    if uses_concept_rel and not linked_to_concept_rel:
        warnings.append(
            f"Warning: Query uses 'concept_relationship' table but it may not be properly joined "
            f"to the clinical tables."
        )

    return len(warnings) == 0, warnings


def _verify_maps_to_direction(tree: exp.Expression, aliases: Dict[str, str]) -> Tuple[bool, List[str]]:
    """
    Verify that 'Maps to' relationship is used in the correct direction:
    - concept_id_1 should be the source concept
    - concept_id_2 should be the standard concept

    Returns (is_valid, list_of_warnings)
    """
    warnings: List[str] = []

    if not _uses_table(tree, "concept_relationship"):
        return True, []

    if not _uses_maps_to_relationship(tree):
        return True, []

    join_conditions = _extract_join_conditions(tree, aliases)

    # Look for joins involving concept_relationship
    for lt, lc, rt, rc in join_conditions:
        # Check if concept_relationship.concept_id_2 is joined to clinical standard field
        # This is the correct direction for 'Maps to' (source -> standard)
        if lt == "concept_relationship" and lc == "concept_id_2":
            # This is correct - concept_id_2 is the target (standard) concept
            pass
        elif rt == "concept_relationship" and rc == "concept_id_2":
            # Also correct
            pass
        elif lt == "concept_relationship" and lc == "concept_id_1":
            # concept_id_1 should be the source, if it's joined to a standard field, warn
            standard_fields = {normalize_name(c) for _, c in STANDARD_CONCEPT_FIELDS}
            if rc in standard_fields:
                warnings.append(
                    f"Warning: 'Maps to' relationship may be used in reverse direction. "
                    f"concept_relationship.concept_id_1 (source) is joined to {rt}.{rc} "
                    f"which is a standard concept field. Consider using concept_id_2 instead."
                )
        elif rt == "concept_relationship" and rc == "concept_id_1":
            standard_fields = {normalize_name(c) for _, c in STANDARD_CONCEPT_FIELDS}
            if lc in standard_fields:
                warnings.append(
                    f"Warning: 'Maps to' relationship may be used in reverse direction. "
                    f"concept_relationship.concept_id_1 (source) is joined to {lt}.{lc} "
                    f"which is a standard concept field. Consider using concept_id_2 instead."
                )

    return len(warnings) == 0, warnings


def _parse_sql(sql: str, dialect: str = "postgres") -> Tuple[Optional[List[exp.Expression]], Optional[str]]:
    """
    Parse SQL and return list of statement trees.
    Handles multiple statements (UNION, etc.) and returns parse errors gracefully.

    Returns (list_of_trees, error_message)
    """
    try:
        # Use parse() instead of parse_one() to handle multiple statements
        trees = sqlglot.parse(sql, read=dialect)
        if not trees:
            return None, "Failed to parse SQL: empty result"
        return trees, None
    except ParseError as e:
        return None, f"SQL parse error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error parsing SQL: {str(e)}"


def _process_single_tree(
    tree: exp.Expression,
    standard_fields: Set[Tuple[str, str]],
    source_fields: Set[Tuple[str, str]]
) -> Tuple[List[str], List[str], Set[str], Set[str]]:
    """
    Process a single SQL tree and return errors, warnings, and field sets.

    Returns (errors, warnings, used_standard_fields_strs, used_source_fields_strs)
    """
    errors: List[str] = []
    warnings: List[str] = []

    aliases = _extract_aliases(tree)
    refs = _extract_concept_references(tree, aliases)

    used_standard = {(t, c) for (t, c) in refs if (t, c) in standard_fields}
    used_source = {(t, c) for (t, c) in refs if (t, c) in source_fields}

    used_standard_strs = sorted({f"{t}.{c}" for (t, c) in used_standard})
    used_source_strs = sorted({f"{t}.{c}" for (t, c) in used_source})

    # If no standard fields used, rule doesn't apply
    if not used_standard:
        return [], [], set(used_standard_strs), set(used_source_strs)

    has_standard_enforcement = _enforces_standard_concept(tree)
    has_maps_to = _uses_maps_to_relationship(tree)

    # Check the main rule: must have either standard enforcement OR maps_to
    if not has_standard_enforcement and not has_maps_to:
        errors.append(
            f"OMOP Semantic Rule Violation: Query uses STANDARD concept fields but does not ensure "
            f"standard concepts. Must either: (A) filter with concept.standard_concept = 'S', or "
            f"(B) use concept_relationship.relationship_id = 'Maps to'. "
            f"STANDARD fields referenced: {', '.join(used_standard_strs)}"
            + (f", SOURCE fields referenced: {', '.join(used_source_strs)}" if used_source_strs else "")
        )

    # Additional verification: JOIN path
    _, join_warnings = _verify_concept_join_path(tree, aliases, used_standard)
    warnings.extend(join_warnings)

    # Additional verification: Maps to direction
    if has_maps_to:
        _, direction_warnings = _verify_maps_to_direction(tree, aliases)
        warnings.extend(direction_warnings)

    return errors, warnings, set(used_standard_strs), set(used_source_strs)


# =========================
# 3) Rule 1: Standard concept mapping required
# =========================

def validate_standard_concept_mapping(sql: str, dialect: str = "postgres") -> List[str]:
    """
    OMOP semantic rule:
    If query uses a STANDARD OMOP concept field, it must either:
      - enforce concept.standard_concept = 'S'
      OR
      - use mapping via concept_relationship relationship_id = 'Maps to'

    Returns list of error messages. Empty list means validation passed.
    """
    # Parse SQL
    trees, parse_error = _parse_sql(sql, dialect)
    if parse_error:
        return [parse_error]

    # Known standard/source fields from schema lists
    standard_fields: Set[Tuple[str, str]] = {
        (normalize_name(t), normalize_name(c)) for t, c in STANDARD_CONCEPT_FIELDS
    }
    source_fields: Set[Tuple[str, str]] = {
        (normalize_name(t), normalize_name(c)) for t, c in SOURCE_CONCEPT_FIELDS
    }

    all_errors: List[str] = []
    all_warnings: List[str] = []

    # Process each statement (handles UNION, multiple statements, etc.)
    for tree in trees:
        if tree is None:
            continue

        # Process the main tree (which includes subqueries in its traversal)
        errors, warnings, _, _ = _process_single_tree(tree, standard_fields, source_fields)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    # Combine errors and warnings (warnings are informational)
    return all_errors + all_warnings


# =========================
# 4) Rule 2: Unmapped concept (concept_id = 0) handling
# =========================

# Clinical tables where concept_id = 0 is semantically important
CLINICAL_CONCEPT_ID_COLUMNS = {
    "condition_occurrence": {"condition_concept_id", "condition_source_concept_id"},
    "drug_exposure": {"drug_concept_id", "drug_source_concept_id"},
    "procedure_occurrence": {"procedure_concept_id", "procedure_source_concept_id"},
    "measurement": {"measurement_concept_id", "measurement_source_concept_id"},
    "observation": {"observation_concept_id", "observation_source_concept_id"},
    "device_exposure": {"device_concept_id", "device_source_concept_id"},
    "visit_occurrence": {"visit_concept_id", "visit_source_concept_id"},
    "visit_detail": {"visit_detail_concept_id", "visit_detail_source_concept_id"},
    "death": {"cause_concept_id", "cause_source_concept_id"},
    "specimen": {"specimen_concept_id", "specimen_source_concept_id"},
    "episode": {"episode_concept_id", "episode_source_concept_id"},
    "person": {"gender_concept_id", "race_concept_id", "ethnicity_concept_id"},
}


def _is_numeric_literal(e: exp.Expression, value: int = None) -> bool:
    """Check if expression is a numeric literal, optionally with specific value."""
    if not isinstance(e, exp.Literal) or e.is_string:
        return False
    try:
        num_val = int(e.this)
        if value is not None:
            return num_val == value
        return True
    except (ValueError, TypeError):
        return False


def _infer_table_for_column(
    col_name: str,
    aliases: Dict[str, str]
) -> Optional[str]:
    """
    For unqualified columns, try to infer the table from CLINICAL_CONCEPT_ID_COLUMNS.
    Returns the table name if the column uniquely matches one clinical table.
    """
    matching_tables = []
    for table, columns in CLINICAL_CONCEPT_ID_COLUMNS.items():
        if col_name in columns:
            # Check if this table is in the query (via aliases)
            if table in aliases.values():
                matching_tables.append(table)

    # Only return if we have exactly one match
    if len(matching_tables) == 1:
        return matching_tables[0]
    return None


def _extract_concept_id_filters(
    tree: exp.Expression,
    aliases: Dict[str, str]
) -> List[Tuple[str, str, exp.Expression]]:
    """
    Find all filters on *_concept_id columns with specific numeric values.

    Returns list of (table, column, filter_expression) tuples.
    """
    filters: List[Tuple[str, str, exp.Expression]] = []

    # Check equality comparisons: concept_id = 12345
    for eq in tree.find_all(exp.EQ):
        if not _is_in_where_or_join_clause(eq):
            continue

        left, right = eq.left, eq.right

        # Normalize: Column = number
        if isinstance(right, exp.Column) and _is_numeric_literal(left):
            left, right = right, left

        if not isinstance(left, exp.Column):
            continue

        col_name = normalize_name(left.name)
        if not (col_name.endswith("_concept_id") or col_name == "concept_id"):
            continue

        # Check if it's a specific numeric value (not 0)
        if _is_numeric_literal(right) and not _is_numeric_literal(right, 0):
            table, _ = _resolve_table_col(left, aliases)
            # If no table prefix, try to infer from clinical tables
            if not table:
                table = _infer_table_for_column(col_name, aliases)
            if table:
                filters.append((table, col_name, eq))

    # Check IN clauses: concept_id IN (12345, 67890)
    for in_expr in tree.find_all(exp.In):
        if not _is_in_where_or_join_clause(in_expr):
            continue

        if not isinstance(in_expr.this, exp.Column):
            continue

        col_name = normalize_name(in_expr.this.name)
        if not (col_name.endswith("_concept_id") or col_name == "concept_id"):
            continue

        # Check if IN clause contains specific numeric values
        has_specific_values = False
        for val in in_expr.expressions or []:
            if _is_numeric_literal(val) and not _is_numeric_literal(val, 0):
                has_specific_values = True
                break

        if has_specific_values:
            table, _ = _resolve_table_col(in_expr.this, aliases)
            # If no table prefix, try to infer from clinical tables
            if not table:
                table = _infer_table_for_column(col_name, aliases)
            if table:
                filters.append((table, col_name, in_expr))

    return filters


def _handles_zero_concept_id(
    tree: exp.Expression,
    aliases: Dict[str, str],
    table: str,
    column: str
) -> bool:
    """
    Check if the query explicitly handles concept_id = 0 for the given column.

    Patterns that indicate handling:
    - column = 0
    - column != 0 / column <> 0
    - column > 0
    - column IS NOT NULL AND column != 0
    - COALESCE(column, 0)
    - CASE WHEN column = 0 THEN ...
    """
    # Check for equality with 0: column = 0
    for eq in tree.find_all(exp.EQ):
        left, right = eq.left, eq.right

        if isinstance(right, exp.Column) and _is_numeric_literal(left, 0):
            left, right = right, left

        if isinstance(left, exp.Column) and _is_numeric_literal(right, 0):
            resolved_table, resolved_col = _resolve_table_col(left, aliases)
            if resolved_col == column:
                if not resolved_table or resolved_table == table:
                    return True

    # Check for inequality with 0: column != 0 or column <> 0
    for neq in tree.find_all(exp.NEQ):
        left, right = neq.left, neq.right

        if isinstance(right, exp.Column) and _is_numeric_literal(left, 0):
            left, right = right, left

        if isinstance(left, exp.Column) and _is_numeric_literal(right, 0):
            resolved_table, resolved_col = _resolve_table_col(left, aliases)
            if resolved_col == column:
                if not resolved_table or resolved_table == table:
                    return True

    # Check for > 0: column > 0
    for gt in tree.find_all(exp.GT):
        left, right = gt.left, gt.right

        if isinstance(left, exp.Column) and _is_numeric_literal(right, 0):
            resolved_table, resolved_col = _resolve_table_col(left, aliases)
            if resolved_col == column:
                if not resolved_table or resolved_table == table:
                    return True

    # Check for >= 1: column >= 1 (equivalent to > 0 for integers)
    for gte in tree.find_all(exp.GTE):
        left, right = gte.left, gte.right

        if isinstance(left, exp.Column) and _is_numeric_literal(right, 1):
            resolved_table, resolved_col = _resolve_table_col(left, aliases)
            if resolved_col == column:
                if not resolved_table or resolved_table == table:
                    return True

    # Check for COALESCE usage
    for coalesce in tree.find_all(exp.Coalesce):
        for arg in coalesce.expressions or [coalesce.this]:
            if isinstance(arg, exp.Column):
                resolved_table, resolved_col = _resolve_table_col(arg, aliases)
                if resolved_col == column:
                    if not resolved_table or resolved_table == table:
                        return True

    # Check for CASE WHEN column = 0
    for case in tree.find_all(exp.Case):
        for when in case.args.get("ifs", []):
            if isinstance(when, exp.If):
                cond = when.this
                if isinstance(cond, exp.EQ):
                    left, right = cond.left, cond.right
                    if isinstance(right, exp.Column) and _is_numeric_literal(left, 0):
                        left, right = right, left
                    if isinstance(left, exp.Column) and _is_numeric_literal(right, 0):
                        resolved_table, resolved_col = _resolve_table_col(left, aliases)
                        if resolved_col == column:
                            if not resolved_table or resolved_table == table:
                                return True

    return False


def validate_unmapped_concept_handling(sql: str, dialect: str = "postgres") -> List[str]:
    """
    OMOP semantic rule:
    When filtering clinical tables by specific *_concept_id values,
    warn if concept_id = 0 (unmapped records) is not explicitly handled.

    In OMOP CDM, concept_id = 0 means "no matching concept was found" during ETL.
    Queries that filter on specific concept_ids may silently exclude these
    unmapped records, which could lead to incomplete results.

    Returns list of warning messages. Empty list means no warnings.
    """
    trees, parse_error = _parse_sql(sql, dialect)
    if parse_error:
        return []  # Don't add warnings if we can't parse

    warnings: List[str] = []

    for tree in trees:
        if tree is None:
            continue

        aliases = _extract_aliases(tree)

        # Find all concept_id filters with specific values
        concept_filters = _extract_concept_id_filters(tree, aliases)

        # Group by (table, column) to avoid duplicate warnings
        checked: Set[Tuple[str, str]] = set()

        for table, column, _ in concept_filters:
            key = (table, column)
            if key in checked:
                continue
            checked.add(key)

            # Check if this is a clinical table concept_id column
            is_clinical = False
            for clinical_table, clinical_cols in CLINICAL_CONCEPT_ID_COLUMNS.items():
                if table == clinical_table and column in clinical_cols:
                    is_clinical = True
                    break

            if not is_clinical:
                continue

            # Check if concept_id = 0 is explicitly handled
            if not _handles_zero_concept_id(tree, aliases, table, column):
                warnings.append(
                    f"Warning: Query filters {table}.{column} by specific value(s) but does not "
                    f"explicitly handle concept_id = 0 (unmapped records). Records where the source "
                    f"code could not be mapped to a standard concept will be silently excluded. "
                    f"Consider adding '{column} > 0' to explicitly exclude unmapped, or handle them separately."
                )

    return warnings


# =========================
# 5) One public entry point
# =========================

def validate_omop_semantic_rules(sql: str, dialect: str = "postgres") -> List[str]:
    """
    Runs all OMOP semantic validations and returns combined errors/warnings.

    Args:
        sql: The SQL query to validate
        dialect: SQL dialect (default: postgres)

    Returns:
        List of error/warning messages. Empty list means validation passed.
    """
    results: List[str] = []
    results.extend(validate_standard_concept_mapping(sql, dialect))
    results.extend(validate_unmapped_concept_handling(sql, dialect))
    return results


__all__ = [
    "validate_standard_concept_mapping",
    "validate_unmapped_concept_handling",
    "validate_omop_semantic_rules",
    "SemanticValidationError",
]
