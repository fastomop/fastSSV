"""
Vocabulary validation rules for OMOP SQL queries.

Rules implemented:
1. No string identification of clinical concepts (don't use LIKE/= on *_source_value columns)
2. Clinical table filtering should include *_concept_id conditions when identifying clinical events
"""

from typing import List, Tuple, Dict, Set, Optional
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


# =========================
# 1) Configuration / Rules
# =========================

# Pairs of (table_name, column_name) where a standard code in the column should be used instead of string.
SOURCE_VALUE_COLUMNS = {
    # Clinical event tables
    ("condition_occurrence", "condition_source_value"),
    ("drug_exposure", "drug_source_value"),
    ("drug_exposure", "route_source_value"),
    ("drug_exposure", "dose_unit_source_value"),
    ("procedure_occurrence", "procedure_source_value"),
    ("procedure_occurrence", "modifier_source_value"),
    ("measurement", "measurement_source_value"),
    ("measurement", "unit_source_value"),
    ("measurement", "value_source_value"),
    ("observation", "observation_source_value"),
    ("observation", "unit_source_value"),
    ("observation", "qualifier_source_value"),
    ("device_exposure", "device_source_value"),
    ("visit_occurrence", "visit_source_value"),
    ("visit_occurrence", "admitted_from_source_value"),
    ("visit_occurrence", "discharged_to_source_value"),
    ("visit_detail", "visit_detail_source_value"),
    ("visit_detail", "admitted_from_source_value"),
    ("visit_detail", "discharged_to_source_value"),
    # Person and death
    ("person", "gender_source_value"),
    ("person", "race_source_value"),
    ("person", "ethnicity_source_value"),
    ("death", "cause_source_value"),
    # Specimen
    ("specimen", "specimen_source_value"),
    ("specimen", "unit_source_value"),
    ("specimen", "anatomic_site_source_value"),
    ("specimen", "disease_status_source_value"),
    # Episode
    ("episode", "episode_source_value"),
    # Note
    ("note", "note_source_value"),
    # Payer
    ("payer_plan_period", "payer_source_value"),
    ("payer_plan_period", "plan_source_value"),
    ("payer_plan_period", "sponsor_source_value"),
    ("payer_plan_period", "stop_reason_source_value"),
}

# Pairs of (table_name, column_name); These are concept-table string columns (allowed only in concept_id lookup context)
CONCEPT_STRING_COLUMNS = {
    ("concept", "concept_name"),
    ("concept", "concept_code"),
    ("concept", "vocabulary_id"),
    ("concept", "domain_id"),
    ("concept", "concept_class_id"),
    ("concept_synonym", "concept_synonym_name"),
    ("concept_ancestor", "min_levels_of_separation"),
    ("concept_ancestor", "max_levels_of_separation"),
    ("vocabulary", "vocabulary_name"),
    ("vocabulary", "vocabulary_reference"),
    ("vocabulary", "vocabulary_version"),
    ("domain", "domain_name"),
    ("concept_class", "concept_class_name"),
    ("relationship", "relationship_name"),
    ("relationship", "is_hierarchical"),
    ("relationship", "defines_ancestry"),
}

STRING_MATCH_EXP_TYPES = (exp.Like, exp.ILike, exp.RegexpLike)

# Clinical tables and their valid concept_id columns for filtering clinical events
CLINICAL_CONCEPT_ID_COLUMNS = {
    "person": {
        "gender_concept_id", "gender_source_concept_id",
        "race_concept_id", "race_source_concept_id",
        "ethnicity_concept_id", "ethnicity_source_concept_id",
    },
    "condition_occurrence": {
        "condition_concept_id", "condition_source_concept_id",
        "condition_type_concept_id", "condition_status_concept_id",
    },
    "drug_exposure": {
        "drug_concept_id", "drug_source_concept_id",
        "drug_type_concept_id", "route_concept_id", "route_source_concept_id",
    },
    "procedure_occurrence": {
        "procedure_concept_id", "procedure_source_concept_id",
        "procedure_type_concept_id", "modifier_concept_id", "modifier_source_concept_id",
    },
    "measurement": {
        "measurement_concept_id", "measurement_source_concept_id",
        "measurement_type_concept_id", "unit_concept_id", "unit_source_concept_id",
        "operator_concept_id", "value_as_concept_id",
    },
    "observation": {
        "observation_concept_id", "observation_source_concept_id",
        "observation_type_concept_id", "qualifier_concept_id", "qualifier_source_concept_id",
        "unit_concept_id", "value_as_concept_id",
    },
    "device_exposure": {
        "device_concept_id", "device_source_concept_id",
        "device_type_concept_id",
    },
    "visit_occurrence": {
        "visit_concept_id", "visit_source_concept_id",
        "visit_type_concept_id", "admitted_from_concept_id", "discharged_to_concept_id",
    },
    "visit_detail": {
        "visit_detail_concept_id", "visit_detail_source_concept_id",
        "visit_detail_type_concept_id", "admitted_from_concept_id", "discharged_to_concept_id",
    },
    "death": {
        "cause_concept_id", "cause_source_concept_id",
        "death_type_concept_id",
    },
    "specimen": {
        "specimen_concept_id", "specimen_source_concept_id",
        "specimen_type_concept_id", "unit_concept_id",
        "anatomic_site_concept_id", "disease_status_concept_id",
    },
    "episode": {
        "episode_concept_id", "episode_source_concept_id",
        "episode_type_concept_id", "episode_object_concept_id",
    },
    "note": {
        "note_type_concept_id", "note_class_concept_id",
        "encoding_concept_id", "language_concept_id",
    },
    "note_nlp": {
        "note_nlp_concept_id", "note_nlp_source_concept_id",
        "section_concept_id",
    },
}

CLINICAL_TABLES = set(CLINICAL_CONCEPT_ID_COLUMNS.keys())

# Columns that are legitimate non-concept filters (dates, IDs, etc.)
# These should not trigger Rule 2 violations
LEGITIMATE_FILTER_COLUMNS = {
    # Primary keys and foreign keys
    "person_id", "visit_occurrence_id", "visit_detail_id",
    "condition_occurrence_id", "drug_exposure_id", "procedure_occurrence_id",
    "measurement_id", "observation_id", "device_exposure_id",
    "specimen_id", "episode_id", "note_id", "note_nlp_id",
    "provider_id", "care_site_id", "location_id",
    # Date columns
    "condition_start_date", "condition_start_datetime", "condition_end_date", "condition_end_datetime",
    "drug_exposure_start_date", "drug_exposure_start_datetime", "drug_exposure_end_date", "drug_exposure_end_datetime",
    "procedure_date", "procedure_datetime",
    "measurement_date", "measurement_datetime",
    "observation_date", "observation_datetime",
    "device_exposure_start_date", "device_exposure_start_datetime", "device_exposure_end_date", "device_exposure_end_datetime",
    "visit_start_date", "visit_start_datetime", "visit_end_date", "visit_end_datetime",
    "visit_detail_start_date", "visit_detail_start_datetime", "visit_detail_end_date", "visit_detail_end_datetime",
    "death_date", "death_datetime",
    "specimen_date", "specimen_datetime",
    "episode_start_date", "episode_start_datetime", "episode_end_date", "episode_end_datetime",
    "note_date", "note_datetime",
    # Other legitimate columns
    "birth_datetime", "year_of_birth", "month_of_birth", "day_of_birth",
    "quantity", "days_supply", "refills", "stop_reason",
    "value_as_number", "range_low", "range_high",
}


# =========================
# 2) Helpers
# =========================

def normalize_name(s: str) -> str:
    return s.lower().strip()


def _parse_sql(sql: str, dialect: str = "postgres") -> Tuple[Optional[List[exp.Expression]], Optional[str]]:
    """
    Parse SQL and return list of statement trees.
    Handles multiple statements (UNION, etc.) and returns parse errors gracefully.

    Returns (list_of_trees, error_message)
    """
    try:
        trees = sqlglot.parse(sql, read=dialect)
        if not trees:
            return None, "Failed to parse SQL: empty result"
        return trees, None
    except ParseError as e:
        return None, f"SQL parse error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error parsing SQL: {str(e)}"


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
        if t.alias:
            aliases[normalize_name(t.alias)] = real
        aliases[real] = real
    return aliases


def _is_string_literal(e: exp.Expression) -> bool:
    return isinstance(e, exp.Literal) and e.is_string


def _resolve_table_col(col: exp.Column, aliases: Dict[str, str]) -> Tuple[str, str]:
    """
    Resolve exp.Column into (real_table_name, column_name).

    Example:
      c.condition_source_value -> ("condition_occurrence", "condition_source_value")
    """
    col_name = normalize_name(col.name)
    table_name = ""
    if col.table:
        table_alias = normalize_name(col.table)
        table_name = aliases.get(table_alias, table_alias)
    return table_name, col_name


def _is_inside_concept_id_lookup(col_node: exp.Column, aliases: Dict[str, str]) -> bool:
    """
    Returns True if this column is used inside a SELECT that:
    1. Outputs concept_id (directly or via alias)
    2. Is selecting from the concept table (or related vocabulary tables)

    Example allowed contexts:
      SELECT concept_id FROM concept WHERE concept_code = 'E11'
      SELECT c.concept_id AS cid FROM concept c WHERE c.concept_name LIKE '%diabetes%'
      SELECT * FROM concept WHERE vocabulary_id = 'ICD10CM'
    """
    select = col_node.find_ancestor(exp.Select)
    if not select:
        return False

    # Check if this SELECT is from a vocabulary table (concept, concept_synonym, etc.)
    from_clause = select.find(exp.From)
    if from_clause:
        is_from_vocab_table = False
        for table in from_clause.find_all(exp.Table):
            table_name = normalize_name(table.name)
            # Check actual table name, resolving aliases
            real_table = aliases.get(table_name, table_name)
            if real_table in {"concept", "concept_synonym", "concept_ancestor",
                              "concept_relationship", "vocabulary", "domain",
                              "concept_class", "relationship"}:
                is_from_vocab_table = True
                break

        if not is_from_vocab_table:
            return False

    # Check if SELECT contains concept_id in its projection
    for proj in select.expressions or []:
        # Handle SELECT *
        if isinstance(proj, exp.Star):
            return True

        # Handle aliased columns: SELECT concept_id AS cid
        target = proj.this if isinstance(proj, exp.Alias) else proj

        if isinstance(target, exp.Column):
            col_name = normalize_name(target.name)
            if col_name == "concept_id":
                return True
            # Also allow concept_id_1, concept_id_2 for concept_relationship
            if col_name in {"concept_id_1", "concept_id_2"}:
                return True

        # Handle qualified: SELECT c.concept_id
        if isinstance(target, exp.Column) and target.table:
            if normalize_name(target.name) == "concept_id":
                return True

    return False


def _contains_clinical_concept_id_in_filters(
    node: exp.Expression,
    aliases: Dict[str, str],
    clinical_tables_used: Set[str],
) -> bool:
    """
    True if this expression subtree references a clinical table *_concept_id column
    belonging to a clinical table used in the query.
    """
    for col in node.find_all(exp.Column):
        col_name = normalize_name(col.name)

        # Skip if not a concept_id column
        if not (col_name.endswith("_concept_id") or col_name == "concept_id"):
            continue

        # Qualified column: resolve alias -> real table
        if col.table:
            alias = normalize_name(col.table)
            real_table = aliases.get(alias, alias)

            if real_table in clinical_tables_used:
                valid_cols = CLINICAL_CONCEPT_ID_COLUMNS.get(real_table, set())
                if col_name in valid_cols:
                    return True
        else:
            # Unqualified column: check if it's valid for ANY of the clinical tables used
            for table in clinical_tables_used:
                valid_cols = CLINICAL_CONCEPT_ID_COLUMNS.get(table, set())
                if col_name in valid_cols:
                    return True

    return False


def _filter_uses_only_legitimate_columns(
    node: exp.Expression,
    aliases: Dict[str, str],
) -> bool:
    """
    Returns True if the filter expression only uses legitimate non-concept columns
    (dates, IDs, numeric values) and doesn't attempt to identify clinical concepts
    via source_value strings.

    This allows queries like:
      WHERE person_id = 123
      WHERE condition_start_date > '2020-01-01'
    """
    columns_used = list(node.find_all(exp.Column))

    if not columns_used:
        return True

    for col in columns_used:
        col_name = normalize_name(col.name)

        # If it's a legitimate filter column, that's fine
        if col_name in LEGITIMATE_FILTER_COLUMNS:
            continue

        # If it's a concept_id column, that's what we want
        if col_name.endswith("_concept_id") or col_name == "concept_id":
            continue

        # If it's a source_value being compared to a string, that's a problem
        # (but this is caught by Rule 1, not Rule 2)
        if col_name.endswith("_source_value"):
            # This is problematic but handled by Rule 1
            continue

        # Resolve the table
        if col.table:
            alias = normalize_name(col.table)
            real_table = aliases.get(alias, alias)

            # If it's from a vocabulary table, that's fine
            if real_table in {"concept", "concept_synonym", "concept_relationship",
                              "concept_ancestor", "vocabulary", "domain",
                              "concept_class", "relationship"}:
                continue

    return True


def _has_string_comparison_on_clinical_table(
    node: exp.Expression,
    aliases: Dict[str, str],
    clinical_tables_used: Set[str],
) -> bool:
    """
    Returns True if the filter contains string comparisons on clinical table columns
    that could be trying to identify concepts (excluding source_value which is handled by Rule 1).
    """
    # Check for string literals in equality comparisons
    for eq in node.find_all(exp.EQ):
        left, right = eq.left, eq.right

        # Normalize direction
        if isinstance(right, exp.Column) and _is_string_literal(left):
            left, right = right, left

        if not (isinstance(left, exp.Column) and _is_string_literal(right)):
            continue

        col_name = normalize_name(left.name)

        # Skip source_value columns (handled by Rule 1)
        if col_name.endswith("_source_value"):
            continue

        # Skip legitimate columns
        if col_name in LEGITIMATE_FILTER_COLUMNS:
            continue

        # If comparing a non-source_value, non-concept_id column to a string
        # on a clinical table, that might be suspicious
        if left.table:
            alias = normalize_name(left.table)
            real_table = aliases.get(alias, alias)
            if real_table in clinical_tables_used:
                # But only if it's not a stop_reason or similar text field
                if col_name not in {"stop_reason", "sig", "lot_number", "unique_device_id"}:
                    return True

    return False


# =========================
# 3) Rule 1: No string identification of clinical concepts
# =========================

def _check_string_match_violations(
    tree: exp.Expression,
    aliases: Dict[str, str]
) -> List[str]:
    """Check for LIKE/ILIKE/REGEXP violations."""
    errors: List[str] = []

    for node in tree.walk():
        # Handle both positive and negative: LIKE, NOT LIKE, ILIKE, NOT ILIKE
        is_not = False
        check_node = node

        if isinstance(node, exp.Not):
            inner = node.this
            if isinstance(inner, STRING_MATCH_EXP_TYPES):
                is_not = True
                check_node = inner
            else:
                continue
        elif not isinstance(node, STRING_MATCH_EXP_TYPES):
            continue

        left = check_node.this
        right = check_node.expression

        if not isinstance(left, exp.Column):
            continue

        table, col = _resolve_table_col(left, aliases)
        key = (table, col)

        not_prefix = "NOT " if is_not else ""
        op_name = check_node.key.upper() if hasattr(check_node, 'key') else "LIKE"

        # Always error: source_value string matching
        if key in SOURCE_VALUE_COLUMNS or col.endswith("_source_value"):
            errors.append(
                f"String matching on source value: {left.sql()} {not_prefix}{op_name} {right.sql()}. "
                f"Use *_concept_id instead (standard OMOP concept identification)."
            )
            continue

        # Concept table string matching: allowed only in concept_id lookup context
        if key in CONCEPT_STRING_COLUMNS:
            if not _is_inside_concept_id_lookup(left, aliases):
                errors.append(
                    f"String matching on concept table outside concept_id lookup: "
                    f"{left.sql()} {not_prefix}{op_name} {right.sql()}. "
                    f"Prefer filtering by *_concept_id (or ensure this is inside a concept_id subquery)."
                )

    return errors


def _check_equality_violations(
    tree: exp.Expression,
    aliases: Dict[str, str]
) -> List[str]:
    """Check for equality comparison violations (col = 'string')."""
    errors: List[str] = []

    for eq in tree.find_all(exp.EQ):
        left = eq.left
        right = eq.right

        # normalize direction: Column = 'string'
        if isinstance(right, exp.Column) and _is_string_literal(left):
            left, right = right, left

        if not (isinstance(left, exp.Column) and _is_string_literal(right)):
            continue

        table, col = _resolve_table_col(left, aliases)
        key = (table, col)

        # Always error: *_source_value = '...'
        if key in SOURCE_VALUE_COLUMNS or col.endswith("_source_value"):
            errors.append(
                f"String equality on source value: {left.sql()} = {right.sql()}. "
                f"Use *_concept_id instead."
            )
            continue

        # Concept table string equality: allowed only if inside concept_id lookup
        if key in CONCEPT_STRING_COLUMNS:
            if not _is_inside_concept_id_lookup(left, aliases):
                errors.append(
                    f"Concept table string filter outside concept_id lookup: {left.sql()} = {right.sql()}. "
                    f"Prefer filtering via concept_id / *_concept_id."
                )

    return errors


def _check_in_clause_violations(
    tree: exp.Expression,
    aliases: Dict[str, str]
) -> List[str]:
    """Check for IN clause violations (col IN ('val1', 'val2'))."""
    errors: List[str] = []

    for in_expr in tree.find_all(exp.In):
        # Handle NOT IN as well
        is_not = isinstance(in_expr.parent, exp.Not)

        col_expr = in_expr.this
        if not isinstance(col_expr, exp.Column):
            continue

        # Check if any values in IN clause are strings
        has_string_values = False
        string_values = []
        for val in in_expr.expressions or []:
            if _is_string_literal(val):
                has_string_values = True
                string_values.append(val.sql())

        if not has_string_values:
            continue

        table, col = _resolve_table_col(col_expr, aliases)
        key = (table, col)

        not_prefix = "NOT " if is_not else ""
        values_str = ", ".join(string_values[:3])
        if len(string_values) > 3:
            values_str += ", ..."

        # Always error: *_source_value IN ('...')
        if key in SOURCE_VALUE_COLUMNS or col.endswith("_source_value"):
            errors.append(
                f"String IN clause on source value: {col_expr.sql()} {not_prefix}IN ({values_str}). "
                f"Use *_concept_id instead."
            )
            continue

        # Concept table string IN: allowed only if inside concept_id lookup
        if key in CONCEPT_STRING_COLUMNS:
            if not _is_inside_concept_id_lookup(col_expr, aliases):
                errors.append(
                    f"Concept table string IN clause outside concept_id lookup: "
                    f"{col_expr.sql()} {not_prefix}IN ({values_str}). "
                    f"Prefer filtering via concept_id / *_concept_id."
                )

    return errors


def validate_concept_identification(sql: str, dialect: str = "postgres") -> List[str]:
    """
    OMOP rule:
    - Do NOT identify clinical concepts using string matching on *_source_value.
    - Allow concept table string filters only when used to produce concept_id.

    Returns list of error messages. Empty list means validation passed.
    """
    trees, parse_error = _parse_sql(sql, dialect)
    if parse_error:
        return [parse_error]

    all_errors: List[str] = []

    for tree in trees:
        if tree is None:
            continue

        aliases = _extract_aliases(tree)

        # Check all violation types
        all_errors.extend(_check_string_match_violations(tree, aliases))
        all_errors.extend(_check_equality_violations(tree, aliases))
        all_errors.extend(_check_in_clause_violations(tree, aliases))

    return all_errors


# =========================
# 4) Rule 2: If filtering clinical tables by concept, must use clinical *_concept_id in WHERE/JOIN
# =========================

def validate_clinical_concept_filters(
    sql: str, dialect: str = "postgres"
) -> List[str]:
    """
    OMOP rule (relaxed version):
    If the query filters clinical event tables and appears to be identifying clinical concepts,
    those filters should include a clinical table *_concept_id condition.

    This rule does NOT flag:
    - Queries that only filter by date, person_id, or other legitimate columns
    - Queries that filter vocabulary tables in a subquery context

    Returns list of error messages. Empty list means validation passed.
    """
    trees, parse_error = _parse_sql(sql, dialect)
    if parse_error:
        return [parse_error]

    all_errors: List[str] = []

    for tree in trees:
        if tree is None:
            continue

        aliases = _extract_aliases(tree)

        # Detect clinical tables used
        used_tables: Set[str] = set(normalize_name(t.name) for t in tree.find_all(exp.Table))
        clinical_used = set(t for t in used_tables if t in CLINICAL_TABLES)

        if not clinical_used:
            continue  # Not applicable

        # Collect filter nodes (WHERE + JOIN ON)
        filter_nodes: List[exp.Expression] = []
        filter_texts: List[str] = []

        where = tree.find(exp.Where)
        if where and where.this:
            filter_nodes.append(where.this)
            filter_texts.append("WHERE " + where.this.sql(dialect=dialect))

        for j in tree.find_all(exp.Join):
            on_expr = j.args.get("on")
            if on_expr:
                filter_nodes.append(on_expr)
                filter_texts.append("JOIN ON " + on_expr.sql(dialect=dialect))

        if not filter_nodes:
            continue  # No filtering at all - that's fine

        # Check if any filter uses clinical concept_id
        has_concept_id_filter = any(
            _contains_clinical_concept_id_in_filters(n, aliases, clinical_used)
            for n in filter_nodes
        )

        if has_concept_id_filter:
            continue  # Good - using concept_id

        # Check if filters only use legitimate columns (dates, IDs)
        # If so, don't flag as a violation
        all_legitimate = all(
            _filter_uses_only_legitimate_columns(n, aliases)
            for n in filter_nodes
        )

        # Check if there are string comparisons trying to identify concepts
        has_suspicious_string_comparison = any(
            _has_string_comparison_on_clinical_table(n, aliases, clinical_used)
            for n in filter_nodes
        )

        # Only flag if there's a suspicious string comparison
        # Don't flag simple date/ID filters
        if all_legitimate and not has_suspicious_string_comparison:
            continue

        clinical_tables_str = ", ".join(sorted(clinical_used))

        suggestions = []
        for t in sorted(clinical_used):
            cols = sorted(CLINICAL_CONCEPT_ID_COLUMNS.get(t, set()))
            if cols:
                suggestions.append(f"- {t}: use one of {', '.join(cols)}")

        suggestion_text = "\n".join(suggestions)
        filters_display = "\n".join(f"  - {f}" for f in filter_texts)

        all_errors.append(
            "OMOP Vocabulary Rule Violation:\n"
            "Clinical concepts should be identified using *_concept_id columns.\n\n"
            f"Clinical tables detected: {clinical_tables_str}\n\n"
            "Filters found in query:\n"
            f"{filters_display}\n\n"
            "No clinical *_concept_id filtering was found.\n\n"
            "Suggested concept_id columns per table:\n"
            f"{suggestion_text}"
        )

    return all_errors


# =========================
# 5) One public entry point
# =========================

def validate_omop_vocabulary_rules(sql: str, dialect: str = "postgres") -> List[str]:
    """
    Runs all OMOP vocabulary validations and returns combined errors/warnings.

    Args:
        sql: The SQL query to validate
        dialect: SQL dialect (default: postgres)

    Returns:
        List of error/warning messages. Empty list means validation passed.
    """
    errors: List[str] = []
    errors.extend(validate_concept_identification(sql, dialect))
    errors.extend(validate_clinical_concept_filters(sql, dialect))
    return errors


__all__ = [
    "validate_concept_identification",
    "validate_clinical_concept_filters",
    "validate_omop_vocabulary_rules",
]
