# The single substep — two candidate designs (session R.6)

Written before plan group 4 is started, as `docs/review/plan.md` asks ("Before 4.1, write
`docs/review/substep_design.md` and stop for the owner") and ruling 10 requires. Nothing
below is built. The owner picks a design, and answers the two questions at the end, before
the first edit to `response._integrate_kernel`.

## Where the kernel stands (`1eeb6d4`)

`_integrate_kernel` is 202 lines: 7 arguments, complexity 23 (ruff C901; radon 32), 89
statements, nesting 3, 183 code lines. Two loops hold the same substep:

| step | forced loop (transit and forced phases) | free-decay loop |
|---|---|---|
| parity offset, per sample | `(sample_number - 1) * substep_count - substep_index` | `(sample_number - 1) * substep_count + 1 - substep_index` |
| unbalance force | `float(unbalance_force_by_substep[i])` | (none) |
| record-frame predicate | stride, capacity | stride, capacity, `sample_number <= nominal_forced_sample_count * 2` |
| state before (trace only) | `v_before = v`, `a_before = a` | the same |
| column advance | `moc.step((substep_index + parity_offset) % 2 == 0, a * dt, column, junction_force)` | the same |
| applied force, coupled | `junction_force + unbalance_force` | `junction_force` |
| applied force, lumped | `0.0 + unbalance_force` | `0.0` |
| SDOF step | `step_scalars(x, v, a, applied_force, sdof_params, dt)` | the same |
| frame: phase | `PHASE_TRANSIT if substep_index < transit_substep_count else PHASE_FORCED` | `PHASE_FREE_DECAY` |
| frame: elbow A, B, unbalance | `elbow_a_force_by_substep[i]`, `elbow_b_force_by_substep[i]`, `unbalance_force` | `0.0`, `0.0`, `0.0` |
| frame: the rest | substep and sample index, `x v a`, friction, stick flag, junction force | the same |
| maxima | `|a|`, `|v|`, `|x|`, `|unbalance_force|` | `|a|`, `|v|`, `|x|` |
| after the substep | | `x * x_zero <= 0.01` sets `x_zero = 0.0` |
| per sample | `_record_sample` if `output_type > 0` | the same, and only while `sample_number <= nominal_forced_sample_count * 2` |

Three facts the designs rest on, each checked against the code:

1. **In the forced loop `i == substep_index`.** `sample_start[0] == 0`, the sample ranges
   are contiguous, and `substep_index` starts at 0 and gains 1 per inner iteration. So the
   frame's phase, elbow forces and unbalance force are a function of `substep_index` and the
   schedule alone: below `len(unbalance_force_by_substep)` they are the schedule's values
   (the phase from `transit_substep_count`), from there on free decay (`PHASE_FREE_DECAY`,
   `0.0`, `0.0`, `0.0`). Reading them that way copies the same doubles. The elbow arrays are
   empty on an untraced run, so they may be read only on a recorded substep.
2. **The column advance does not touch the SDOF state** (`moc.step` reads `a * dt`, writes
   the column arrays, returns the junction force). So the "state before" the trace needs is
   the state the SDOF step receives; `v_before` / `a_before` become the step's inputs.
3. **The applied force needs the junction force the column advance returns.** Whoever
   computes the applied force must run after the column advance. If the caller computes it
   (as the brief expects, so each loop keeps its expression verbatim), the caller also
   advances the column, and the order column -> SDOF is written in each loop.

## Decisions common to both designs

* **The applied force is computed by the caller**, each loop keeping its own two
  expressions verbatim (`junction_force + unbalance_force` / `0.0 + unbalance_force`;
  `junction_force` / `0.0`). They are never merged (`0.0 + F` is not `F` for `F = -0.0`,
  `docs/architecture.md` "Exactness notes"). Therefore the column advance stays in the
  loops too (fact 3), before the helper call: the order column -> SDOF is unchanged and
  visible.
* **The unbalance-force maximum leaves the loop.** It is the largest `abs()` over the
  schedule, which the forced loop visits entry by entry, in order, exactly once. A compiled
  `_largest_magnitude(unbalance_force_by_substep)` with the same comparison (`if abs(f) >
  m: m = abs(f)`, from 0.0) returns the same double for every input, NaN and `-0.0`
  included; no arithmetic. It lets the shared code ignore the unbalance force.
* **The free-decay re-test stays in the free-decay loop**, after each substep, so the
  overflow check of `_free_decay_product` (D-23) runs at the same points.
* **No `inline='always'`, no `fastmath`** (`docs/style.md` §4, the brief).
* **Python mode.** Each design adds one or two Python calls per substep under
  `NUMBA_DISABLE_JIT=1`; the pure-Python lumped path will be slower by an amount the bench
  will show (the compiled paths are the ones the 5 % limit has been applied to so far, and
  the A/B below covers them). Flagged, not hidden.

## Design A (recommended) — one substep function

The loops keep what differs (parity offset, unbalance force, column advance, applied
force, the free-decay re-test, the history window); everything they share is one compiled
function. The trace is recorded inside it (by `_trace_frame`, still its own function).

```python
class _RunState(NamedTuple):
    """What one substep changes: the SDOF state, the running maxima and the counters."""
    x: float               # m
    v: float               # m/s
    a: float               # m/s²
    x_max: float           # largest |x| so far, m
    v_max: float
    a_max: float
    substep_index: int     # running 0-based substep counter
    frame_count: int       # trace frames written


class _SubstepInputs(NamedTuple):
    """What a substep reads and never changes; built once per kernel call."""
    sdof_params: SdofParams
    substep_duration: float
    schedule: _ForceSchedule   # for the frame's phase and elbow forces (fact 1)
    buffers: tracing.TraceBuffers
    column: moc.FluidColumn    # read by the frame writer only


@numba.njit(cache=True)
def _advance_structure(
    state: _RunState,
    applied_force: float,
    junction_force: float,
    sample_index: int,
    is_in_record_window: bool,
    inputs: _SubstepInputs,
) -> _RunState:
    """One SDOF substep under ``applied_force``: step, record a trace frame if one is due,
    update the maxima, count the substep."""
```

Its body, in order: the record-frame predicate (stride, capacity, `is_in_record_window`);
`step_scalars(x, v, a, applied_force, sdof_params, dt)`; if recording, `_trace_frame` with
the frame labels read by `substep_index` (fact 1) and the friction / stick values from the
input state (fact 2); the three `if abs(.) > max` trackers in today's order (`a`, `v`,
`x`); `substep_index + 1`; return a new `_RunState`.

The kernel then reads:

```python
for s in range(forced_sample_count):
    sample_number += 1
    parity_offset = _parity_offset(settings, sample_number, state.substep_index, 0)
    for i in range(sample_start[s], sample_start[s + 1]):
        unbalance_force = float(unbalance_force_by_substep[i])
        if is_fluid_coupled:
            junction_force = float(moc.step(
                (state.substep_index + parity_offset) % 2 == 0, state.a * dt, column, junction_force
            ))
            applied_force = junction_force + unbalance_force
        else:
            applied_force = 0.0 + unbalance_force
        state = _advance_structure(state, applied_force, junction_force, sample_number - 1, True, inputs)
    _record_sample(response_history, output_type, sample_number - 1, state.x, state.v, state.a)
unbalance_force_max = _largest_magnitude(unbalance_force_by_substep)

forced_samples = sample_number
decay_start_displacement = state.x
while _free_decay_product(state.x, decay_start_displacement) > FREE_DECAY_THRESHOLD:
    sample_number += 1
    parity_offset = _parity_offset(settings, sample_number, state.substep_index, 1)
    is_in_record_window = sample_number <= nominal_forced_sample_count * 2
    for _k in range(substep_count):
        if is_fluid_coupled:
            junction_force = float(moc.step(
                (state.substep_index + parity_offset) % 2 == 0, state.a * dt, column, junction_force
            ))
            applied_force = junction_force
        else:
            applied_force = 0.0
        state = _advance_structure(state, applied_force, junction_force, sample_number - 1,
                                   is_in_record_window, inputs)
        decay_start_displacement = _decay_reference(state.x, decay_start_displacement)
    if is_in_record_window:
        _record_sample(response_history, output_type, sample_number - 1, state.x, state.v, state.a)
```

* **Applied force:** the caller (above).
* **Maxima:** carried in the returned `_RunState` (`docs/style.md` §4: scalars that evolve
  are passed in and returned); no array, no memory traffic in the compiled loop.
* **Trace:** inside the substep function, as a call to `_trace_frame`; the frame labels
  come from the schedule by `substep_index`, so the loops pass only the history-window
  flag.
* **Numba rule K-1:** the column goes kernel -> `moc.step` (one deep, as now) and kernel ->
  `_advance_structure` -> `_trace_frame` (two deep, on recorded substeps only). R.2's toy
  measured a cost for a tuple passed two deep on every substep; here the second level is
  entered once per `trace_every` substeps. The A/B decides.
* **Estimated kernel:** complexity 8 (two `for`, one `while`, one `for`, two
  `if is_fluid_coupled`, one window `if`, plus 1), about 45 lines, 6 arguments once the
  junction force starts in the kernel (step 0 below).

## Design B — two short loops sharing per-concern helpers

No substep function. Each loop body is a fixed sequence of calls, one per concern, as
`docs/style.md` §3 states it ("stepping and recording are separate functions"). This is
plan 4.6 and 4.7 without 4.9, the fallback the plan names.

```python
@numba.njit(cache=True)
def _track_peaks(peaks: np.ndarray, x: float, v: float, a: float) -> None:
    """Raise peaks[0..2] (|x|, |v|, |a|) to the new state, in today's order a, v, x."""


@numba.njit(cache=True)
def _record_frame(
    recorder: _FrameRecorder,      # (schedule, buffers, column), built once per kernel call
    frame_count: int,
    key: _FrameKey,                # (substep_index, sample_index, is_in_record_window)
    before: tuple[float, float],   # v, a before the step (friction, stick)
    after: tuple[float, float, float],
    junction_force: float,
) -> int:
    """Write the frame if one is due (stride, capacity, window); return the frame count."""
```

Each loop body becomes (forced; free decay differs in the force lines and the window flag,
and adds the re-test):

```python
        unbalance_force = float(unbalance_force_by_substep[i])
        if is_fluid_coupled:
            junction_force = float(moc.step((substep_index + parity_offset) % 2 == 0, a * dt, column, junction_force))
            applied_force = junction_force + unbalance_force
        else:
            applied_force = 0.0 + unbalance_force
        x_new, v_new, a_new = step_scalars(x, v, a, applied_force, sdof_params, dt)
        frame_count = _record_frame(recorder, frame_count, _FrameKey(substep_index, sample_number - 1, True),
                                    (v, a), (x_new, v_new, a_new), junction_force)
        x, v, a = x_new, v_new, a_new
        _track_peaks(peaks, x, v, a)
        substep_index += 1
```

* **Applied force:** the caller, as in A.
* **Maxima:** a three-element float64 array `peaks`, updated in place (§4: arrays are
  updated in place); unpacked into `_KernelResult` at the end.
* **Trace:** a concern of its own, called from both loops; the column goes one deep only.
* **Estimated kernel:** complexity 8, about 60 lines; the substep is still written twice,
  as six calls and the force lines, so the two loops can be compared by eye but are not
  one.

## Why A

* It is what the review is for (C-02, plan 4.9): the shared substep exists once, and what
  differs between the phases is exactly what is left in the loops. In B the six-line
  sequence is still duplicated, now as calls.
* The maxima stay in registers in A; B's array is a memory store per substep in the
  lumped path, where the substep is cheapest and a few per cent is easiest to lose.
* The cost of A is K-1's second level for `_trace_frame` and `_SubstepInputs` nesting two
  tuples; both are measured by the A/B before anything else is built on them.

## The commits (design A), each with `make clean-cache`, the gates, the snapshot in both modes, `tools/bench.py` and an A/B against the commit before

0. (R4) The kernel starts the junction force at 0.0 and no longer returns it: after
   ruling 49 `_integrate` always passes 0.0 and nothing reads the returned value
   (`_KernelResult.junction_force`); 7 -> 6 arguments. Proposed, not made.
1. (4.9a, R4) `_RunState`, `_SubstepInputs`, `_advance_structure` extracted from the forced
   loop, every expression moved verbatim; the frame labels read from the schedule at
   `substep_index` (equal to `i`, fact 1). The forced loop keeps its unbalance-force
   tracker for now. The free-decay loop is untouched.
2. (4.9b, R4) The free-decay loop calls `_advance_structure`; the frame-label read gains
   the free-decay branch (`substep_index >= len(unbalance_force_by_substep)`).
3. (4.9c, R2/R3) What is left, one per commit: `_largest_magnitude` for the
   unbalance-force maximum; `_parity_offset` (the two formulas differ only by the VBA's
   first `k`, 0 or 1; integers, ruling 25); the record-frame predicate as one function;
   the per-sample history write (`_record_sample` already writes nothing unless
   `output_type` is 1 to 3, so the `output_type > 0` guards go; the free-decay window
   stays at its call site); `_decay_reference` for the re-test;
   `junction_force if is_fluid_coupled else 0.0` in the frame becomes `junction_force`
   (without a column it is the 0.0 it started as, never reassigned).

If a commit is not bit-identical, it is reverted (charter rule 3) and the session stops. If
reaching complexity under 10 needs an arithmetic change, the session stops and reports.

## Questions for the owner

* **Q-R6-1, the plan's order.** `plan.md` puts 4.1 to 4.8 (compiled
  `effective_displacement`, the `moc.step` split, the junction-force functions, one column
  advance, the friction / stick function, peak trackers, the trace writers, `_trace_frame`
  to `trace.py`) before 4.9, and ruling 46 makes the plan win. The brief asks for the
  substep in this session. Recommended: 4.9 now (steps 0 to 3 above), because 4.1 to 4.5
  change callees and do not depend on the loop shape, and 4.6 / 4.7 would build per-loop
  trackers and writers that 4.9 then moves again (design A absorbs 4.6: the maxima live
  in `_advance_structure`). 4.1 to 4.5, 4.7, 4.8, 4.10 and 4.12 stay open for a later
  session. Or follow the plan's order and leave 4.9 to the end of group 4.
* **Q-R6-2, step 0.** Make it (kernel 7 -> 6 arguments, the dead returned junction force
  gone), or leave the kernel signature as it is?
