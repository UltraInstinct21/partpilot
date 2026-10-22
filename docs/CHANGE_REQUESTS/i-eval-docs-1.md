# Change request 1: add matplotlib to the backend dependencies

**From:** i-eval-docs
**To:** orchestrator
**Date:** 2026-10-22
**Files I may not edit:** `backend/pyproject.toml` (owned by the orchestrator)

## What I need

The plan section 6.1 lists `matplotlib` for the data work and the charts.
The backend `pyproject.toml` has `pandas` and `numpy` but not `matplotlib`.

The evaluation package (`eval/charts.py`) needs `matplotlib` to write the
five charts of the report. The charts are:

* the field accuracy per tier;
* the cost per tier;
* the field accuracy per manufacturer;
* the confusion matrix of the validation experiment;
* the cost against the accuracy.

## Why it matters

The CI job cannot write the charts without the package. The report needs the
PNG files in `eval/results/`.

## The change

Add one line to the `dependencies` list of `backend/pyproject.toml`:

```toml
  "matplotlib>=3.9,<4",
```

Then refresh the lock file:

```bash
cd backend && uv lock && uv sync --python 3.12
```

## What I did in the meantime

`eval/charts.py` imports `matplotlib` inside the functions and not at the
top of the module. When the package is missing, the functions raise
`eval.charts.ChartsUnavailable` with a clear message. The command
`python -m eval charts <results.json>` then prints that message and returns
the exit code 2. The rest of the harness (the metrics, the gold set, the
runners and the demo) works without `matplotlib`.

The chart tests use `pytest.importorskip("matplotlib")`, so they are skipped
and not failed when the package is missing.

## Note for the build machine

The package was installed in the working virtual environment with:

```bash
uv pip install --python backend/.venv/bin/python matplotlib
```

This is only a local fix. The dependency must be in `pyproject.toml` and in
`uv.lock` so that a clean checkout has it.
