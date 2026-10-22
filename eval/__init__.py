"""PartPilot evaluation harness (plan WP8).

The package is deliberately standalone. It never imports another agent's
package, never opens a database connection and never calls a network API.
Every runner takes the implementation it measures through injection, so the
same harness measures the fake implementations in the tests and the real ones
in the manual scripts.

Modules:

* ``eval.metrics`` - the pure metric functions.
* ``eval.gold_set`` - the gold set loader, validator and agreement report.
* ``eval.runners`` - the six experiments of plan WP8.
* ``eval.charts`` - the matplotlib charts.
* ``eval.queries`` - the 30 natural-language search queries.
* ``eval.demo`` - a fixture backed demo that runs with no network.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
