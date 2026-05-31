#!/usr/bin/env bash
#
# Run the same checks as the `lint-and-test` job in .github/workflows/ci.yml,
# in the same order, against the project virtualenv. Run this before every
# commit/push so CI failures surface locally first.
#
# Keep this script in lockstep with ci.yml: if a step is added, removed, or
# reordered there, mirror the change here (and vice versa).
#
# Usage:
#   ./scripts/check.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUFF="$ROOT/.venv/bin/ruff"
PYLINT="$ROOT/.venv/bin/pylint"
PYTEST="$ROOT/.venv/bin/pytest"

echo "==> [1/4] ruff check ."
"$RUFF" check .

echo "==> [2/4] ruff format --check ."
"$RUFF" format --check .

echo "==> [3/4] pylint (all tracked *.py)"
# shellcheck disable=SC2046  # word-splitting of the file list is intended
"$PYLINT" $(git ls-files '*.py')

echo "==> [4/4] pytest"
# Mirror CI: a pytest exit code of 5 means "no tests collected", which CI
# treats as success.
"$PYTEST" --tb=short || {
    code=$?
    if [ "$code" -eq 5 ]; then
        echo "No tests collected."
    else
        exit "$code"
    fi
}

echo
echo "==> All CI checks passed."
