"""Session V.1: the solver trace (``trace_every``) and ``loads.elbow_forces``.

The trace must not change what the solvers compute: every test here that runs a solver
compares the traced ``PeakResponse`` with the untraced one bitwise, and the untraced path
itself stays pinned to ``legacy_port`` by ``tests/test_differential.py``.
"""

from __future__ import annotations

import numpy as np
import pytest
import test_differential as td
import test_golden as tg

from surge_sdof import loads

# ------------------------------------------------------------------ loads.elbow_forces


def _loads_args(kw):
    return (kw["sample_freq"], kw["physical_length"], kw["celerity"], kw["step_qty"])


def _check_elbow_forces(force, kw):
    """``elbow_forces`` and ``unbalance_force`` walk the same samples; ``fa - fb`` is the
    unbalance value bitwise; the phase flips once, after the truncated delay sample."""
    unbalance = list(loads.unbalance_force(force, *_loads_args(kw)))
    elbows = list(loads.elbow_forces(force, *_loads_args(kw)))
    assert len(elbows) == len(unbalance)
    phases = []
    for (phase, fa, fb), u in zip(elbows, unbalance, strict=True):
        assert len(fa) == len(fb) == len(u)
        assert all(type(a) is float and type(b) is float for a, b in zip(fa, fb, strict=True))
        assert [a - b for a, b in zip(fa, fb, strict=True)] == u
        phases.append(phase)
    n_elements = int(np.size(force))
    n_delay = len(unbalance) - n_elements
    assert phases == [0] * n_delay + [1] * n_elements
    # the delay phase holds forceA at the first history sample
    first = float(np.asarray(force, dtype=float).reshape(-1, order="F")[0])
    assert all(a == first for _phase, fa, _fb in elbows[:n_delay] for a in fa)
    return elbows


@pytest.mark.parametrize("idx", range(td.N_CASES), ids=td.SWEEP_IDS)
def test_elbow_forces_split_the_unbalance_force_on_the_sweep(idx):
    case = td.sweep_cases()[idx]
    _check_elbow_forces(case.force, case.kw)


def test_elbow_forces_split_the_unbalance_force_on_the_example_case():
    case = next(c for c in tg.EXAMPLE_CASES if c["solver"] == "lumped")
    force = np.asarray(case["force_history"], dtype=float)
    _check_elbow_forces(force, case["kwargs"])


def test_elbow_forces_split_the_unbalance_force_on_the_golden_history():
    case = next(c for c in tg.CASES if c["solver"] == "lumped")
    _check_elbow_forces(tg.load_force(tg.PARAMS), tg.case_params(case, tg.PARAMS))


def test_elbow_forces_raise_as_unbalance_force_does():
    case = td.sweep_cases()[0]
    kw = dict(case.kw, step_qty=1)
    with pytest.raises(ZeroDivisionError):  # D-7
        next(loads.elbow_forces(case.force, *_loads_args(kw)))
    with pytest.raises(IndexError):  # D-8, the single-row history of test_differential
        list(loads.elbow_forces(np.ones((1, 10)), 100.0, 100.0, 1000.0, 10))
