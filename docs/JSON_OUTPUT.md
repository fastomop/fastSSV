# JSON Output Format for FastSSV Validation

## Overview

FastSSV outputs validation results in JSON format for structured, machine-readable results. This enables integration with automated systems, APIs, and CI/CD pipelines.

## Usage

### Command Line

FastSSV produces JSON output by default:

```bash
# Basic usage - outputs JSON
python main.py your_query.sql

# With other options
python main.py your_query.sql --dialect mysql
python main.py your_query.sql --categories semantic
python main.py your_query.sql --rules semantic.standard_concept_enforcement
```

## JSON Structure

### Single Query Output

For a single query, the output structure is:

```json
{
  "query": "SELECT ...",
  "dialect": "postgres",
  "is_valid": true,
  "error_count": 0,
  "warning_count": 0,
  "violations": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | The SQL query that was validated (normalized, whitespace collapsed) |
| `dialect` | string | SQL dialect used for parsing (e.g., "postgres", "mysql", "duckdb") |
| `is_valid` | boolean | True if no ERROR-level violations, false otherwise |
| `error_count` | number | Count of ERROR-level violations |
| `warning_count` | number | Count of WARNING-level violations |
| `violations` | array | List of violation objects (empty if valid) |

### Multiple Queries Output

When the SQL file contains multiple queries (separated by semicolons), the output structure is:

```json
{
  "total_queries": 3,
  "valid_queries": 2,
  "invalid_queries": 1,
  "results": [
    {
      "query_index": 1,
      "query": "SELECT ...",
      "dialect": "postgres",
      "is_valid": true,
      "error_count": 0,
      "warning_count": 0,
      "violations": []
    },
    ...
  ]
}
```

### Violation Object

Each violation in the `violations` array has this structure:

```json
{
  "rule_id": "semantic.standard_concept_enforcement",
  "message": "Detailed error message...",
  "severity": "ERROR",
  "location": "optional location info"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rule_id` | string | Unique identifier for the rule (e.g., "semantic.join_path_validation") |
| `message` | string | Human-readable violation message |
| `severity` | string | "ERROR" or "WARNING" |
| `location` | string | Optional location information (file, line, SQL fragment) |

## Examples

### Valid Query

```bash
$ python main.py test_valid.sql
```

```json
{
  "query": "SELECT p.person_id FROM person p JOIN location l ON p.location_id = l.location_id WHERE p.gender_concept_id = 8507;",
  "dialect": "postgres",
  "is_valid": true,
  "error_count": 0,
  "warning_count": 0
}
```

Note: `violations` array is omitted when empty.

### Invalid Query - Multiple Violations

```bash
$ python main.py test_query.sql
```

```json
{
  "query": "SELECT c.person_id, x.concept_name FROM condition_occurrence c JOIN concept x ON x.concept_id = c.condition_concept_id WHERE x.concept_name = 'Hypertension';",
  "dialect": "postgres",
  "is_valid": false,
  "error_count": 3,
  "warning_count": 0,
  "violations": [
    {
      "rule_id": "semantic.join_path_validation",
      "message": "Join direction looks reversed: concept -> condition_occurrence. Expected condition_occurrence.condition_concept_id = concept.concept_id",
      "severity": "ERROR",
      "location": ""
    },
    {
      "rule_id": "semantic.standard_concept_enforcement",
      "message": "Query uses STANDARD OMOP concept fields but does not enforce standard concepts...",
      "severity": "ERROR",
      "location": ""
    },
    {
      "rule_id": "vocabulary.concept_string_filter",
      "message": "Concept table string filter outside concept_id lookup: x.concept_name = 'Hypertension'",
      "severity": "WARNING",
      "location": ""
    }
  ]
}
```

### Multiple Queries

```bash
$ python main.py queries.sql
```

```json
{
  "total_queries": 2,
  "valid_queries": 1,
  "invalid_queries": 1,
  "results": [
    {
      "query_index": 1,
      "query": "SELECT ...",
      "dialect": "postgres",
      "is_valid": true,
      "error_count": 0,
      "warning_count": 0
    },
    {
      "query_index": 2,
      "query": "SELECT ...",
      "dialect": "postgres",
      "is_valid": false,
      "error_count": 1,
      "warning_count": 0,
      "violations": [...]
    }
  ]
}
```

## Programmatic Usage

The JSON output is designed for integration with other systems. Here are common patterns:

### Python

```python
import json
import subprocess

# Run FastSSV (outputs JSON by default)
result = subprocess.run(
    ["python", "main.py", "query.sql"],
    capture_output=True,
    text=True
)

# Parse JSON
validation = json.loads(result.stdout)

# Check if valid
if validation["is_valid"]:
    print("Query is valid")
else:
    print(f"{validation['error_count']} errors, {validation['warning_count']} warnings")
    for violation in validation.get("violations", []):
        severity_icon = "ERROR" if violation["severity"] == "ERROR" else "WARNING"
        print(f"{severity_icon} [{violation['rule_id']}] {violation['message']}")

# Check exit code
if result.returncode != 0:
    print("Validation failed")
else:
    print("Validation passed")
```

### Direct Python API

```python
from fastssv import validate_sql_structured

# Get structured violations
violations = validate_sql_structured(sql, dialect="postgres")

# Check results
if not violations:
    print("Valid")
else:
    for v in violations:
        print(f"{v.severity}: [{v.rule_id}] {v.message}")

# Filter by category
violations = validate_sql_structured(sql, categories=["semantic"])

# Filter by specific rules
violations = validate_sql_structured(
    sql,
    rule_ids=["semantic.standard_concept_enforcement"]
)
```

### JavaScript/Node.js

```javascript
const { exec } = require('child_process');

exec('python main.py query.sql', (error, stdout, stderr) => {
  if (error) {
    console.error('Execution error:', error);
    return;
  }

  const validation = JSON.parse(stdout);

  // Process results
  if (validation.is_valid) {
    console.log('Query is valid');
  } else {
    console.log(`${validation.error_count} errors found`);

    validation.violations?.forEach(v => {
      console.log(`${v.severity}: [${v.rule_id}] ${v.message}`);
    });
  }
});
```

### CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Validate SQL Queries

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'

      - name: Install FastSSV
        run: |
          python -m pip install -e .

      - name: Validate SQL queries
        run: |
          for sql_file in queries/*.sql; do
            echo "Validating $sql_file..."
            python main.py "$sql_file" > result.json
            if [ $? -ne 0 ]; then
              cat result.json | jq '.violations'
              exit 1
            fi
          done
```

Or with a helper script `check_validation.py`:

```python
import json
import sys
import subprocess
import glob

failed = False
for sql_file in glob.glob("queries/*.sql"):
    result = subprocess.run(
        ["python", "main.py", sql_file],
        capture_output=True,
        text=True
    )

    validation = json.loads(result.stdout)

    if not validation["is_valid"]:
        print(f"FAILED {sql_file}: {validation['error_count']} errors")
        for v in validation.get("violations", []):
            print(f"  [{v['rule_id']}] {v['message']}")
        failed = True

if not failed:
    print("All validations passed")

sys.exit(1 if failed else 0)
```

## Exit Codes

FastSSV uses standard exit codes:

- **0**: All validations passed (no ERROR-level violations)
- **1**: One or more ERROR-level violations found

Note: WARNING-level violations do not cause non-zero exit codes.

This enables proper shell scripting and CI/CD integration:

```bash
python main.py query.sql && echo "Success" || echo "Failed"
```

## Schema Version

The JSON structure may evolve in future versions. Consider defensive parsing:

```python
validation = json.loads(output)

# Check for single vs multiple query format
if "results" in validation:
    # Multiple queries
    for result in validation["results"]:
        process_result(result)
else:
    # Single query
    process_result(validation)
```

Current structure should be treated as version 1.0.
