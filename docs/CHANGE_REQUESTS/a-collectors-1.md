# Change request 1 (agent A - collection)

**From:** agent A (collection, `backend/collectors/**`)
**To:** the orchestrator (owner of `backend/pyproject.toml`)
**Date:** 2026-10-22

## What

`backend/collectors/manual/` is a Python package (`__init__.py` +
`collect_manual.py`) but the frozen `backend/pyproject.toml` lists the
packages explicitly:

```toml
[tool.setuptools]
packages = [
  "shared",
  "app",
  "collectors",
  "extraction",
  ...
]
```

`collectors.manual` is missing from that list.

## Why

* Without the entry the manual script is not part of an installed wheel
  (`pip install .`), so `python -m collectors.manual.collect_manual` only
  works from a source checkout.
* The script must never run in CI, so it must stay a separate, explicitly
  marked package - that is the reason for the request and not a reason to
  delete it.

## Requested change

```toml
[tool.setuptools]
packages = [
  "shared",
  "app",
  "collectors",
  "collectors.manual",
  "extraction",
  ...
]
```

## Workaround that is already in place

None is needed for the test suite: the tests never import the manual
package and `backend/tests/collectors/` does not touch it. The script is
run from the repository (`cd backend && .venv/bin/python -m
collectors.manual.collect_manual --dry-run`), which works without the
change.

## Not affected

No other frozen file has to change. `shared/config.py`, `shared/schemas.py`,
`shared/interfaces.py` and `shared/db_schema.sql` were used as they are.
