"""The force the fluid column exerts on the structure.

``peak_response`` and ``peak_response_jc`` share one integration loop and differ only in
the coupling object they pass to it. Per sub-step the loop calls
``coupling_force(state, step_index)`` *before* the SDOF update, with the state at the end
of the previous sub-step (the VBA MoC block sits at the top of each ``k`` loop and reads
the current ``a``), and adds the result to the unbalance force (phases 1-2) or uses it
alone (free decay).

``step_index`` is a running sub-step counter over the whole run (0 at the first
sub-step); the JC coupling (a later session) uses its parity for the MoC alternation
(approved fix F-2, NOTES.md). Only ``NoCoupling`` is implemented in Stage 4.1.

This module knows nothing about the force history, output types or the SDOF update.
See ``docs/architecture.md``.
"""

from __future__ import annotations

from typing import Protocol

from surge_sdof.structure import State

__all__ = ["Coupling", "NoCoupling"]


class Coupling(Protocol):
    def coupling_force(self, state: State, step_index: int) -> float:
        """Force on the structure from the fluid at this sub-step (``dF`` in the VBA)."""
        ...


class NoCoupling:
    """The lumped solver (``GetPeakResponse``): no fluid feedback, ``dF = 0``."""

    __slots__ = ()

    def coupling_force(self, state: State, step_index: int) -> float:
        return 0.0
