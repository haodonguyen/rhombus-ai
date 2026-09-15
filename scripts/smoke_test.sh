#!/usr/bin/env bash
# End-to-end check against a running deployment:
#
#   ./scripts/smoke_test.sh http://<host>
#
# Checks health, lists files, submits a find-and-replace job on the sample CSV with an explicit
# regex (so the check does not depend on LLM latency), waits for it and prints a results page.
set -euo pipefail

BASE="${1:?usage: smoke_test.sh <base-url>}"
BASE="${BASE%/}"

api() { curl -fsS -H 'Content-Type: application/json' "$@"; }
field() { python3 -c "import json, sys; print(json.load(sys.stdin)$1)"; }

echo "health: $(api "$BASE/api/health/")"
echo "files:  $(api "$BASE/api/files/" | field '["files"][0]["key"]')"

job=$(api -X POST "$BASE/api/jobs/" -d '{
  "source_key": "samples/customers.csv",
  "target_columns": ["Email"],
  "pattern": "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b",
  "replacement_value": "REDACTED"
}')
id=$(echo "$job" | field '["id"]')
echo "job:    $id"

for _ in $(seq 1 150); do
  state=$(api "$BASE/api/jobs/$id/" | field '["status"]')
  echo "status: $state"
  case "$state" in
    SUCCESS) break ;;
    FAILED) api "$BASE/api/jobs/$id/"; exit 1 ;;
  esac
  sleep 2
done
[ "$state" = SUCCESS ] || { echo "job did not finish in time"; exit 1; }

api "$BASE/api/jobs/$id/results/?page=1&page_size=3" | python3 -m json.tool
