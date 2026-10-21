"""Live home for the VBA comparison semantics the solvers depend on.

``vba_compat.py`` is frozen (Stage 1); new code that needs a VBA semantic that is not
there takes it from this module, so there is one copy that survives the Stage 6 removal
of ``legacy_port.py``.

``vba_min`` / ``vba_max`` are the module-level VBA helpers (``legacy/vba`` lines 3-17)::

    If valueA < valueB Then min = valueA Else min = valueB
    If valueA > valueB Then max = valueA Else max = valueB

The ``Else`` branch is what distinguishes them from Python's built-ins: on a tie, or when
either operand is NaN (every comparison false), the **second** argument is returned, and
with it its type (``vba_max(0, -0.0)`` is ``-0.0``; ``vba_max(0, 1.5)`` is ``1.5`` but
``vba_max(0, -1.5)`` is the int ``0``). Python's ``min``/``max`` return the first argument
in both situations. The solvers write ``min(...)``/``max(...)`` exactly where the VBA does,
so the tie/NaN/sign-of-zero behaviour is preserved bitwise.
"""

from __future__ import annotations

__all__ = ["vba_min", "vba_max"]


def vba_min(value_a, value_b):
    """VBA ``min``: ``valueA`` if ``valueA < valueB`` else ``valueB``."""
    if value_a < value_b:
        return value_a
    else:
        return value_b


def vba_max(value_a, value_b):
    """VBA ``max``: ``valueA`` if ``valueA > valueB`` else ``valueB``."""
    if value_a > value_b:
        return value_a
    else:
        return value_b
