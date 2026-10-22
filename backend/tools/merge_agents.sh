#!/usr/bin/env bash
# Merge the agent branches into main, in the order that minimises conflicts.
#
#   backend/tools/merge_agents.sh            # merge every agent branch
#   backend/tools/merge_agents.sh e-data     # merge one branch
#
# After each merge the backend test suite and linters are run. The script
# stops at the first failure so the orchestrator can resolve it.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1

ORDER=(
  e-data
  d-validation
  b-tier1
  c-llm
  a-collectors
  f-services
  g-api
  h-frontend
  i-eval-docs
)

if [ "$#" -gt 0 ]; then
  ORDER=("$@")
fi

run_checks() {
  echo "--- ruff ---"
  (cd backend && .venv/bin/python -m ruff check .) || return 1
  echo "--- black ---"
  (cd backend && .venv/bin/python -m black --check .) || return 1
  echo "--- pytest ---"
  (cd backend && .venv/bin/python -m pytest -q) || return 1
  echo "--- eslint ---"
  (cd frontend && npx eslint .) || return 1
  echo "--- prettier ---"
  (cd frontend && npx prettier --check "src/**/*.{ts,tsx,css,json}") || return 1
  echo "--- tsc ---"
  (cd frontend && npx tsc -b) || return 1
  return 0
}

for agent in "${ORDER[@]}"; do
  branch="agent/${agent}"
  echo "=============================================================="
  echo "Merging ${branch}"
  echo "=============================================================="

  if ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
    echo "SKIP: branch ${branch} does not exist"
    continue
  fi

  if ! git merge --no-ff --no-edit "$branch"; then
    echo "CONFLICT while merging ${branch}. Resolve it, then:"
    echo "  git add -A && git commit --no-edit && backend/tools/merge_agents.sh ${agent}"
    exit 2
  fi

  if ! run_checks; then
    echo "CHECKS FAILED after merging ${branch}. Fix and re-run."
    exit 3
  fi
  echo "OK: ${branch} merged and the checks pass."
done

echo "All merges complete."
