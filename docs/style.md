# surge_sdof style guide

Basis: the Google Python Style Guide. The rules below add to it or depart from it, and win where they differ. They apply to the live solver modules. legacy_port.py and vba_compat.py are exempt: they are a literal transcription and stay as written.

## 1. Priorities, in order
1. Results stay bit-identical.
2. An engineer who knows water hammer and structural dynamics, but not this code or the VBA, can follow it.
3. Google style.
4. Metric targets. They are indicators, not goals.

## 2. Names
- Descriptive by default. A name says what the quantity is physically, not how it was computed or what type holds it: closed_gap_stiffness_ratio, not ratio2; transit_delay_samples, not unb. No array, flat, tmp, data, val.
- The wider the scope, the fuller the name. One-letter names only for a loop index used within a few lines.
- Symbols. Inside a kernel, a quantity with an established symbol may use it (x, v, a, dt, rho_c) if it is listed in docs/nomenclature.md with its meaning and unit. Never in a public signature. (Google 3.16.5.)
- Units. Quantities are SI. A quantity that is not SI carries its unit in the name: pressure_drop_bar, flow_rate_m3_per_h.
- Kinds. Counts end in _count, positions in _index, per-sub-step increments say so (friction_velocity_step). Booleans read as predicates (is_short_pipe, record_frame).
- One word per concept, used everywhere: sample, sub-step, frame; node, cell; segment.
- No VBA spellings or VBA naming patterns. docs/nomenclature.md maps each code name to its VBA name.

## 3. Functions
- One job at one level of abstraction. Set-up, stepping and recording are separate functions.
- At most 6 parameters for a private function. Beyond that, group them into a NamedTuple or dataclass named for the thing it describes (the fluid column, the run settings), not for its type.
- Public functions take keyword-only arguments after the first two.
- No argument that selects behaviour or return shape by number or string code where two functions or an enum would do.
- Guard clauses and early returns in place of nested if-blocks.
- No repeated block longer than about five lines.
- Targets: cyclomatic complexity 10, 50 statements, nesting depth 3, and a second look at anything over about 40 lines (Google 3.18). A function that misses a target carries a one-line reason.

## 4. Compiled kernels
- numba.njit(cache=True) only. Never fastmath, parallel or inline='always'.
- Parameters arrive as module-level NamedTuples. Arrays inside them are updated in place. Scalars that evolve are passed in and returned.
- No jitclass, StructRef or typed containers.
- The same source must run and give the same bits with NUMBA_DISABLE_JIT=1.

## 5. Arithmetic is behaviour
- Operand order, grouping, literal type and the form of a power are part of the result. Structural changes move expressions verbatim.
- Any change to an expression is a behaviour change: its own commit, a DEVIATIONS.md row and a test that pins the new value.

## 6. Constants and units
- No bare literal with physical or numerical meaning. Module-level ALL_CAPS constants, each with a comment giving meaning, unit and source. 0, 1 and 2 inside a formula are fine.
- Unit conversion factors are named constants.

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
- None yet. Add a line here, with the reason, for any function that keeps a deliberate departure from this guide.
