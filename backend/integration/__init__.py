"""The integration layer.

The modules here compose the implementation packages of the other agents for
one specific job. They are the only place that may use more than one of them
at a time; everything else talks through the protocols of
``shared.interfaces``.
"""

from __future__ import annotations

__all__ = ["datasheet_seed"]
