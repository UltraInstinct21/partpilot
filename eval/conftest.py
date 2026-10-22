"""Make the ``eval`` package importable from the repository root.

The evaluation package lives in the repository root, not in ``backend``. The
backend virtual environment runs the tests of the evaluation package with::

    cd backend && .venv/bin/python -m pytest ../eval -q

This file adds the repository root to ``sys.path``, so ``import eval.metrics``
works in every case.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
