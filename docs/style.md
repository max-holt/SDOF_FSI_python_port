# surge_sdof style guide

Basis: the Google Python Style Guide. The rules below add to it or depart from it, and win where they differ. They apply to the modules in the scope of docs/review/charter.md: the solver core and the supporting Python. legacy_port.py and vba_compat.py are exempt: they are a literal transcription and stay as written.

## 1. Priorities, in order
1. Results stay bit-identical.
2. An engineer who knows water hammer and structural dynamics, but not this code or the VBA, can follow it.
3. Google style.
4. Metric targets. They are indicators, not goals.

## 2. Names
- Descriptive by default. A name says what the quantity is physically, not how it was computed or what type holds it: closed_gap_stiffness_ratio, not ratio2; transit_delay_samples, not unb. No array, flat, tmp, data, val.
- The wider the scope, the fuller the name. One-letter names only for a loop index used within a few lines.
- Symbols. Inside a kernel, a quantity with an established symbol may use it (x, v, a, dt, rho_c) if it is listed in docs/nomenclature.md with its meaning and unit. A compiled kernel may use listed symbols in its signature too. Never in a public signature. (Google 3.16.5.)
- Public signature means the user-facing entry points: the solver entry points in response, histories.canonical, every function in histories.py that a tool calls, and the export.to_*_dict functions (owner's rulings, R.1b and R.3). A function that other modules or the tests call is not public in this sense.
- Units. Quantities are SI. A quantity that is not SI carries its unit in the name: pressure_drop_bar, flow_rate_m3_per_h. Exception (owner's ruling, R.9): the five duration terms of a pressure history (lead_in_s, transit_s, tail_s, decay_s, duration_s) keep their _s, because the bare words would be ambiguous with the sample counts.
- Kinds. Counts end in _count, positions in _index, per-substep increments say so (friction_velocity_step). Booleans read as predicates (is_short_pipe, record_frame).
- One word per concept, used everywhere: sample, substep (one word), frame; node, cell; segment.
- Vocabulary (owner's rulings, R.1b and R.3). The two staggered half-grids are A and B (pressure_a, velocity_b): node for A, cell for B. An entry of the interleaved display grid is a grid point. The elbows are A and B: elbow A is the one the pressure wave reaches first (the inlet side of the run), elbow B is reached after the transit delay. The load phases are transit, forced and free decay.
- No VBA spellings or VBA naming patterns. docs/nomenclature.md maps each code name to its VBA name. Internal names change in the renames session; public keywords and the names in exported files change in the public API session, and stay as they are until then.

## 3. Functions
- One job at one level of abstraction. Set-up, stepping and recording are separate functions.
- At most 6 parameters, as ruff counts them (PLR0913); keyword-only parameters count (owner's ruling, R.3). Beyond that, group them into a NamedTuple or dataclass named for the thing it describes (the fluid column, the run settings), not for its type. The limit is enforced in the public API session; before it, it is a target.
- The user-facing Python entry points take keyword-only arguments after the first two. Compiled functions do not: they take positional parameter objects, because on Numba 0.68 a compiled function with keyword-only parameters cannot be called from another compiled function.
- No argument that selects behaviour or return shape by number or string code where two functions would do. An on/off choice is a plain flag. The junction-coupling flags (vav_denominator, parity, fraction_profile) and output_type are the known cases: both flag paths must keep working, their form is redesigned in the public API session and is not touched before it.
- Readability over abstraction (owner's ruling, R.1b). No protocol, base class, enum or wrapper layer unless it has two real users today. A function or class that only tests call is removed, and its tests are pointed at the code that actually runs, with their assertions unchanged. A NamedTuple or dataclass parameter object (above, and section 4) is not a layer in this sense.
- Guard clauses and early returns in place of nested if-blocks.
- No repeated block longer than about five lines.
- Targets: cyclomatic complexity 10, 50 statements, nesting depth 3, and a second look at anything over about 40 lines (Google 3.18). A function that misses a target carries a one-line reason.
- Complexity is as ruff counts it (C901). radon's count is reported in docs/review/baseline.md and is not a target.

## 4. Compiled kernels
- numba.njit(cache=True) only. Never fastmath, parallel or inline='always'.
- Parameters arrive as module-level NamedTuples. Arrays inside them are updated in place. Scalars that evolve are passed in and returned.
- No jitclass, StructRef or typed containers.
- A function called on every substep takes only scalars and small tuples of scalars. Arrays are passed only to functions that are called once per run or that loop over them internally (owner's ruling, R.6: a substep function passed the schedule, trace buffers and fluid column was not inlined and cost 12-100 %).
- The same source must run and give the same bits with NUMBA_DISABLE_JIT=1.

## 5. Arithmetic is behaviour
- Operand order, grouping, literal type and the form of a power are part of the result. Structural changes move expressions verbatim.
- Any change to an expression is a behaviour change: its own commit, a DEVIATIONS.md row and a test that pins the new value.
- The rule is about floating point. Precomputing an exact integer product (out_max * 2) is not an expression change (owner's ruling, R.3).

## 6. Constants and units
- No bare literal with physical or numerical meaning. Module-level ALL_CAPS constants, each with a comment giving meaning, unit and source. 0, 1 and 2 inside a formula are fine.
- Unit conversion factors are named constants. Each factor is named in place, where its literal stands today, and factors are never folded together: 60 * 60 stays two factors, because one constant of 3600 changes the grouping (section 5).
- A pure-number coefficient of a formula (4 / 3, 12) stays inline, with a comment giving its derivation. A derivation that cannot be found in the code, the VBA or the documents is asked of the owner, not guessed.

## 7. Docstrings and comments (departure from Google)
- Numpy-style sections: Parameters, Returns, Raises, Notes. The package already uses them throughout and they are the convention of the numerical Python libraries.
- First line: what the function computes, in the model's terms.
- Every physical argument and return states its unit.
- Equations, VBA line references and DEVIATIONS ids go in Notes.
- Comments say why, never what. A comment that restates the line below it is deleted.

## 8. Formatting (departure from Google)
- 100 columns, not 80. Equation-heavy lines read better unbroken. ruff format decides everything else.

## 9. Types
- Every function signature is annotated. Array arguments state shape and dtype in the docstring.

## 10. Changes
- One refactoring per commit, named in the message. Gates as in docs/review/charter.md. Revert on red.

## 11. Recorded exceptions
- Add a line here, with the reason, for any function that keeps a deliberate departure from this guide. A user-facing entry point that still exceeds the 6-argument limit after the public API session is recorded here (owner's ruling, R.3).
- `moc.step` keeps its `is_even_substep` flag (one function for the two half-grid updates; section 3 asks for two functions). Splitting it either adds a parity branch to each kernel loop or needs a column advance that passes the column two calls deep per substep, which section 4 rules out (owner's ruling, R.7; plan 4.2 to 4.4 dropped).
- `response._integrate_kernel` keeps 55 statements as ruff counts them, above the target of 50. What remains is the two frame-label blocks and the two `moc.step` calls of its two loops; shortening them further would hide the substep sequence (owner's ruling, R.8).
- `response.peak_response_jc` takes 7 parameters (`force_history`, `sample_rate`, `span`, `restraint`, `fluid`, `integration`, `coupling`), above the limit of 6. The sample rate describes the history, not its integration, and stays beside it so that changing the integration settings cannot mis-state the history's rate (owner's ruling, R.9).
- `loads.unbalance_force` and `loads.elbow_forces` keep a nesting depth of 4, above the target of 3. The fourth level comes from the phase dispatch inside the per-sample loop: each consumer loops over the items of `_schedule` (level 1) and tells a transit sample from a forced one (`isinstance(item, _TransitSample)`, level 2), which puts the substep loop at level 3 and the transit-delay stop inside it at level 4. Removing the dispatch needs `_schedule` restructured so that each phase reaches its consumer without one, which is the schedule change deferred with finding C-07 (the two walks, open by decision; the one-walk form cost about 20 % on the compiled lumped path) and needs an A/B (owner's rulings, R.8 and R.10; finding L1 of the close-out).
- `histories.step_sine` (9 parameters as ruff counts them) and `histories.step_noise` (12) are above the limit of 6: their parameters are the sweep's generator columns one-for-one (`PARAM_KEYS`; `from_params` takes a row and passes them by name), and grouping them would split one flat column set into objects that the sweep must take apart again (owner's rulings, R.3 no. 17 and R.9 on `docs/review/public_interface.md` §3.4).
- `histories.canonical` (14 parameters) is above the limit of 6. Its parameters are not the generator columns: it is not called by `from_params`, and two of its three positional parameters (`design_pressure`, `amplitude_fraction`) are not in `PARAM_KEYS`. It is a public entry point (section 2) that builds a sweep history from a case: three positional parameters that choose the generator and set the peak, and eleven keyword-only parameters, each one generator parameter under the generator's own name, of which a caller passes only those its history type uses (the sweep passes five). Grouping the eleven would put mostly unused optional fields into one object per call. The signature is the one approved in `docs/review/public_interface.md` §2.2 (owner's ruling, R.9); ruling 90 accepted an earlier reason that described the generators, not this function (finding H4 of the close-out).
- `response._record_frame` takes the trace buffers and, through `_FrameInputs`, the fluid column, and the kernel calls it inside the substep loop, which section 4 reserves for functions of scalars. It runs only on a recorded substep (behind `if record_frame:`, never when `trace_every` is 0), and the arrays are what it writes; the trace write stays in each loop as this one call (owner's ruling 56, R.6; finding R19 of the close-out).
- `tools/review_ab.py` and `tools/review_baseline.py` are under the lint exemption of the tools no test runs (`pyproject.toml` `per-file-ignores`; owner's ruling 87), although the review uses them as gates: the A/B timing and the metrics. No test runs either, a person reads their output, and their measurements do not depend on their own structure; `review_ab.main` nests 4 deep.
- Functions over about 40 code lines (section 3's second look; code lines are the function's lines less its docstring), each with its reason:
  - `moc.step` (103): one function for the two half-grid updates (the `is_even_substep` line above), each written as the VBA's MoC block with scalar loop bodies and no per-cell helper calls so it compiles whole; 13 of its lines are the "For Ben to review" comment on the odd-step tap (D-24).
  - `loads._schedule` (92): the transit and forced walks hand the elbow-B position over as local variables, so the two phases sit in one generator; splitting them needs that hand-over made explicit, a change to the walk deferred to Stage 6 with an A/B (finding L2); 4 of its lines are the "For Ben to review" comment on the transit bound.
  - `loads.unbalance_force` (70) and `loads.elbow_forces` (68): a 13-line unpack of the walk constants, then the phase dispatch of the nesting line above with the VBA's inner `k` loops written out per phase; the unpack is repeated in both and goes with the C-07 restructure.
  - `response.peak_response_jc` (62): the set-up of `GetPeakResponseJC` in the VBA's order, straight-line apart from the short-pipe fallback; 15 lines are the `_trace_request` call with the literal `inputs` echo, kept as a literal because its key order reaches exported bytes (C-11). Sharing the set-up with `peak_response` needs a prefix and a suffix helper (finding R3, Stage 6).
  - `response._kernel_inputs` (55): three set-up jobs, the forces flattened, the response histories allocated and the trace buffers sized; splitting them is finding R4, deferred to Stage 6. No reason beyond that deferral.
  - `trace.build_trace` (55): builds the 23 fields of a `Trace`, the frame columns by the table loop and the junction-coupling column through a positional `ColumnTrace` constructor of 8 values; its two jobs (finding T6) are deferred to Stage 6. No reason beyond that deferral.
  - `viz.geometry.loop_layout` (75): straight-line (complexity 1); 26 lines are the `LoopLayout` constructor by keyword (19 fields) and 28 the rest positions of the five segments, a mask and an assignment per segment. Open finding SP-20 (G2 of the close-out).
  - `histories.step_sine` (50) and `histories.step_noise` (72): each parameter is coerced on entry and echoed into the `History` by keyword, so the length follows from the flat parameter sets recorded above. The coercion prologue shared with `step` is finding H1, deferred to Stage 6.
  - `histories.canonical` (62): the dispatch over the three history types, each generator called with its arguments written out (`step_sine` twice: on a unit amplitude to find the scaling, then scaled); the dispatch repeated in `from_params` is finding H2, deferred to Stage 6.
  - `histories.from_params` (44): the defaults of the four shared duration terms and the per-type call of each generator with its `PARAM_KEYS` by name; the repetition is finding H2, deferred to Stage 6. (The close-out report's list of eleven left this function out.)
