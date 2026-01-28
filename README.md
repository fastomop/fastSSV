# FastSSV — FastOMOP Semantic Static Validator

FastSSV is a **semantic validation framework for OMOP CDM–based analyses**.

FastSSV evaluates whether SQL queries and analytical logic **conform to the semantic, temporal, and vocabulary constraints of the OMOP Common Data Model**, independently of how the SQL was authored (human-written, ATLAS-generated, scripted, or AI-generated).

FastSSV does **not** evaluate model performance or data quality.
It validates the **analysis logic itself**.

---

## Quick Start

### Using uv (Recommended)

1. Install dependencies and run FastSSV:
  ```bash
  uv run python main.py path/to/query.sql
  ```

2. Or set up a development environment:
  ```bash
  uv sync
  source .venv/bin/activate
  python main.py path/to/query.sql
  ```

3. Run the validation unit tests:
  ```bash
  uv run python -m unittest
  ```

### Using pip

1. Create and activate a virtual environment, then install FastSSV in editable mode:
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install -e .
  ```

2. Validate a SQL file (or pipe SQL via stdin):
  ```bash
  python main.py path/to/query.sql
  # or
  cat query.sql | python main.py --dialect duckdb
  ```

3. Run the validation unit tests:
  ```bash
  python -m unittest
  ```

---

## Motivation

In the OMOP ecosystem, SQL is not merely an implementation detail — it is the **formal language of scientific intent**:

- Cohorts are defined in SQL  
- Phenotypes are operationalized in SQL  
- Time-at-risk is encoded in SQL  
- Feature extraction logic is written in SQL  

Existing OHDSI tools focus on:
- **data correctness** (e.g. conformance, plausibility),
- **cohort characterization**,
- **phenotype performance**, or
- **model performance**.

However, **no existing tool validates whether the SQL logic itself is semantically valid under OMOP CDM rules**.

FastSSV fills this gap by providing **static, deterministic validation of analysis logic**.

---

## What FastSSV Validates

FastSSV implements a **plugin-based rule system** organized into categories:

### 1. Semantic Rules (`--categories semantic`)
Validates OMOP CDM schema and concept usage:
- **Join path validation**: Ensures table joins follow CDM schema relationships
- **Standard concept enforcement**: Validates proper use of STANDARD concept fields
- **Maps-to direction**: Checks concept_relationship 'Maps to' relationships
- **Unmapped concept detection**: Detects use of unmapped concepts (concept_id = 0)

### 2. Vocabulary Rules (`--categories vocabulary`)
Validates OMOP vocabulary lookup patterns:
- **String concept ID detection**: Warns against string-based concept lookups
- **Concept table filtering**: Encourages concept_id-based filtering

You can run specific rules:
```bash
# Run all rules (default)
python main.py query.sql

# Run specific categories
python main.py query.sql --categories semantic
python main.py query.sql --categories semantic vocabulary

# Run specific rules
python main.py query.sql --rules semantic.standard_concept_enforcement
```

### Future Rules (Planned)
- **Deep vocabulary validation**: Validate specific vocabularies (SNOMED, RxNorm, LOINC)
- **Temporal validator**: Future information leakage, temporal windows, index dates
- **Logical validator**: Cohort logic preservation (AND/OR/NOT), predicate analysis

FastSSV explicitly detects **silent semantic violations** — cases where SQL executes successfully and returns plausible results, but violates OMOP analytical contracts.

---

## What FastSSV Does *Not* Do

FastSSV intentionally does **not**:

- Evaluate predictive performance (AUC, calibration, etc.)
- Train, tune, or compare models
- Rank AI systems or prompts
- Judge clinical appropriateness
- Replace OHDSI analytical pipelines
- Use large language models as arbiters of correctness

FastSSV is a **validator**, not a benchmark or optimizer.

---

## Static Validation Approach

FastSSV treats SQL validation as a **constraint-checking problem**, similar to static analysis in programming languages.

1. SQL queries are normalized into a **canonical abstract syntax tree (AST)**.
2. An **analysis contract** is defined from:
   - OMOP CDM specifications,
   - scenario metadata,
   - reference SQL templates (when available).
3. Deterministic validators check whether the query satisfies:
   - schema constraints,
   - vocabulary constraints,
   - temporal constraints,
   - logical constraints.
4. FastSSV produces a **validation report** with typed, localized violations.

This approach is:
- deterministic,
- explainable,
- reproducible,
- independent of execution results.

---

## Relationship to AI Systems

FastSSV is **AI-agnostic**.

SQL produced by:
- humans,
- ATLAS,
- scripts,
- AI systems or agents

is validated in exactly the same way.

AI systems are treated as **producers of SQL**, not as objects of evaluation.
This makes FastSSV suitable for AI-assisted analytics **without relying on probabilistic or model-based judgment**.

---

## Position in the OHDSI Ecosystem

FastSSV complements existing OHDSI tools rather than replacing them:

| Layer | Tool |
|-----|------|
| Data correctness | DataQualityDashboard |
| Data characterization | Achilles |
| Cohort inspection | CohortDiagnostics |
| Phenotype validity | PheValuator |
| Model performance | PatientLevelPrediction |
| **Analysis logic validity** | **FastSSV** |

FastSSV validates what other tools **assume to be correct**.

---

## Typical Use Cases

- Detect silent temporal leakage in cohort or feature SQL
- Validate ATLAS-exported cohort definitions
- Audit multi-site study SQL for semantic drift
- Safely integrate AI-generated SQL into OMOP workflows
- Improve reproducibility of observational studies

---

## Example Output

FastSSV produces structured JSON validation output:

```bash
$ python main.py query.sql
```

```json
{
  "query": "SELECT ...",
  "dialect": "postgres",
  "is_valid": false,
  "error_count": 2,
  "warning_count": 0,
  "violations": [
    {
      "rule_id": "semantic.join_path_validation",
      "message": "Invalid join keys for person -> provider...",
      "severity": "ERROR",
      "location": ""
    }
  ]
}
```

For programmatic use:

```python
from fastssv import validate_sql_structured

# Recommended: Returns structured RuleViolation objects
violations = validate_sql_structured(sql)
for v in violations:
    print(f"{v.rule_id}: {v.message}")

# Legacy: Returns dict with error lists
from fastssv import validate_sql
results = validate_sql(sql)
# Returns: {'violations': [...], 'semantic_errors': [...], 'vocabulary_errors': [...]}
```