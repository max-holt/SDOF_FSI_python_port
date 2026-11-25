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
- `response._integrate_kernel` keeps 56 statements, above the target of 50. What remains is the two frame-label blocks and the two `moc.step` calls of its two loops; shortening them further would hide the substep sequence (owner's ruling, R.8).
- `response.peak_response_jc` takes 7 parameters (`force_history`, `sample_rate`, `span`, `restraint`, `fluid`, `integration`, `coupling`), above the limit of 6. The sample rate describes the history, not its integration, and stays beside it so that changing the integration settings cannot mis-state the history's rate (owner's ruling, R.9).
