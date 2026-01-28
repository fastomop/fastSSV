# JSON Output - Quick Reference

## Usage

```bash
# JSON output (default and only format)
python main.py query.sql

# With options
python main.py query.sql --dialect postgres
python main.py query.sql --categories semantic
python main.py query.sql --rules semantic.standard_concept_enforcement
```

## JSON Response Structure

### Single Query - Valid (No Violations)
```json
{
  "query": "SELECT p.person_id FROM person p ...",
  "dialect": "postgres",
  "is_valid": true,
  "error_count": 0,
  "warning_count": 0
}
```

### Single Query - Invalid (With Violations)
```json
{
  "query": "SELECT ...",
  "dialect": "postgres",
  "is_valid": false,
  "error_count": 2,
  "warning_count": 1,
  "violations": [
    {
      "rule_id": "semantic.join_path_validation",
      "message": "Invalid join keys...",
      "severity": "ERROR",
      "location": ""
    },
    {
      "rule_id": "vocabulary.concept_string_filter",
      "message": "Concept table string filter...",
      "severity": "WARNING",
      "location": ""
    }
  ]
}
```

### Multiple Queries
```json
{
  "total_queries": 2,
  "valid_queries": 1,
  "invalid_queries": 1,
  "results": [
    {
      "query_index": 1,
      "query": "...",
      "dialect": "postgres",
      "is_valid": true,
      "error_count": 0,
      "warning_count": 0
    },
    {
      "query_index": 2,
      "query": "...",
      "dialect": "postgres",
      "is_valid": false,
      "error_count": 1,
      "warning_count": 0,
      "violations": [...]
    }
  ]
}
```

## Exit Codes

- **0** = No ERROR-level violations (`is_valid: true`)
- **1** = One or more ERROR-level violations (`is_valid: false`)

Note: WARNING-level violations do not affect exit code.

## Key Fields

### Single Query Response
| Field | Meaning |
|-------|---------|
| `query` | Normalized SQL query (whitespace collapsed) |
| `dialect` | SQL dialect used for parsing |
| `is_valid` | boolean - true if no ERROR-level violations |
| `error_count` | Number of ERROR-level violations |
| `warning_count` | Number of WARNING-level violations |
| `violations` | Array of violation objects (omitted if empty) |

### Violation Object
| Field | Meaning |
|-------|---------|
| `rule_id` | Unique rule identifier (e.g., "semantic.join_path_validation") |
| `message` | Human-readable violation message |
| `severity` | "ERROR" or "WARNING" |
| `location` | Optional location info |

### Multiple Query Response
| Field | Meaning |
|-------|---------|
| `total_queries` | Total number of queries validated |
| `valid_queries` | Count of queries with no ERROR violations |
| `invalid_queries` | Count of queries with ERROR violations |
| `results` | Array of query results with `query_index` |

## Common Parsing Patterns

### Check Overall Status
```python
validation = json.loads(response)
if validation["is_valid"]:
    print("Query is valid")
else:
    print(f"{validation['error_count']} errors, {validation['warning_count']} warnings")
```

### Process All Violations
```python
for violation in validation.get("violations", []):
    severity = violation["severity"]
    print(f"{severity}: [{violation['rule_id']}] {violation['message']}")
```

### Filter by Severity
```python
errors = [v for v in validation.get("violations", []) if v["severity"] == "ERROR"]
warnings = [v for v in validation.get("violations", []) if v["severity"] == "WARNING"]

print(f"Errors: {len(errors)}, Warnings: {len(warnings)}")
```

### Handle Multiple Queries
```python
if "results" in validation:
    # Multiple queries
    for result in validation["results"]:
        status = "VALID" if result['is_valid'] else "INVALID"
        print(f"Query {result['query_index']}: {status}")
else:
    # Single query
    status = "VALID" if validation["is_valid"] else "INVALID"
    print(status)
```

### Use Exit Code in Shell
```bash
python main.py query.sql > result.json
if [ $? -eq 0 ]; then
    echo "Valid"
else
    echo "Invalid"
    cat result.json | jq '.error_count'
fi
```

## Integration Examples

### REST API Endpoint
```python
from flask import Flask, request, jsonify
import subprocess
import json

app = Flask(__name__)

@app.route("/validate", methods=["POST"])
def validate():
    sql = request.json.get("query")
    dialect = request.json.get("dialect", "postgres")

    result = subprocess.run(
        ["python", "main.py", "-", "--dialect", dialect],
        input=sql,
        capture_output=True,
        text=True
    )

    validation = json.loads(result.stdout)
    status_code = 200 if validation["is_valid"] else 400

    return jsonify(validation), status_code
```

### GitHub Actions Workflow
```yaml
- name: Validate SQL with FastSSV
  run: |
    for sql_file in queries/*.sql; do
      python main.py "$sql_file" > result.json
      if [ $? -ne 0 ]; then
        echo "Failed: $sql_file"
        cat result.json | jq '.violations'
        exit 1
      fi
    done
```

### Python Script
```python
import json
import subprocess
import sys

result = subprocess.run(
    ["python", "main.py", "query.sql"],
    capture_output=True,
    text=True
)

validation = json.loads(result.stdout)

# Process violations
if not validation["is_valid"]:
    for v in validation.get("violations", []):
        print(f"[{v['rule_id']}] {v['message']}")

sys.exit(0 if validation["is_valid"] else 1)
```

### Direct Python API
```python
from fastssv import validate_sql_structured

violations = validate_sql_structured(sql, dialect="postgres")

if not violations:
    print("Valid")
else:
    for v in violations:
        print(f"{v.severity}: [{v.rule_id}] {v.message}")
```

## Complete Field Reference

### Single Query Response
```
{
  query: string           // Normalized SQL query
  dialect: string         // SQL dialect (postgres, mysql, etc.)
  is_valid: boolean       // true if no ERROR violations
  error_count: number     // Count of ERROR violations
  warning_count: number   // Count of WARNING violations
  violations?: [          // Array (omitted if empty)
    {
      rule_id: string     // e.g., "semantic.join_path_validation"
      message: string     // Human-readable message
      severity: "ERROR"|"WARNING"
      location: string    // Optional location info
    }
  ]
}
```

### Multiple Query Response
```
{
  total_queries: number       // Total queries in file
  valid_queries: number       // Queries with is_valid=true
  invalid_queries: number     // Queries with is_valid=false
  results: [                  // Array of query results
    {
      query_index: number     // 1-based index
      query: string
      dialect: string
      is_valid: boolean
      error_count: number
      warning_count: number
      violations?: [...]      // Same as single query
    }
  ]
}
```
