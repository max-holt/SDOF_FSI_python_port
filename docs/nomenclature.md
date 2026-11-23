# Nomenclature — proposed (session R.3, for the owner's approval)

**Status: proposal. Nothing has been renamed.** The owner edits and approves this table;
the renames then follow it, one quantity or one tightly related family per commit
(`docs/review/plan.md`, group 1). `docs/style.md` §2 ("Names") is the rule this follows:
descriptive by default; a symbol only inside a compiled kernel, only if it is listed under
"Kernel symbols" below with its meaning and unit, and never in a public signature.

One row per quantity the solver and the supporting modules use. Columns:

* **proposed** — the code name. `?` with a question means I could not tell what the
  quantity is and the owner is asked ("Questions", end).
* **symbol** — an established symbol, where there is one (used in docstrings and Notes;
  in code only as listed under "Kernel symbols").
* **unit** — SI unless the name carries a suffix (ruling 28). "—" for counts, indices,
  flags and dimensionless numbers.
* **VBA** — the name in `legacy/vba/Existing Code.bas` (or the `interpFraction_fix` files);
  "—" where the VBA has none. VBA misspellings are recorded here and nowhere else (ruling
  in the session brief: comments that quote VBA lines stay verbatim).
* **current** — every name the quantity has in Python today, `module.name` where the
  module matters.
* **when** — when the rename is applied:
  * **R** — the renames session (now, after approval): locals, private functions, module
    constants, NamedTuple fields, and parameters of functions that are not public.
  * **K** — with the parameter objects (plan group 3, ruling 21): the parameters and
    locals of the compiled kernels `response._integrate_kernel` and
    `response._trace_frame`, the parameters of `moc.step` and `structure.step_scalars`,
    and the `JunctionCoupling` attributes (replaced by the column NamedTuple of plan 3.2).
    The name is fixed here; it is applied once, as a field or parameter, then.
  * **P** — the public API session: public function names and their parameters (taken
    here as every function without a leading underscore; see question Q-N1), dataclass
    fields returned to users (`PeakResponse`, `Trace`, `LoopLayout`, `History`), and every
    name written into an exported file or a CSV header (the schema bump).
  * **—** — unchanged.

Scope: every parameter and local of `moc.step`, `structure.step_scalars`,
`response._integrate_kernel`, `response._integrate` and `loads._schedule`; the quantities
of the other solver modules and of the supporting modules (`trace.py`, `export.py`,
`histories.py`, `viz/geometry.py`, and the gated tools `tools/sweep_jc.py` (run part) and
`tools/cases.py`); every NamedTuple and dataclass field. A loop index used within a few
lines (`i`, `j`, `k`, `n`, `c`, `s` in a comprehension) keeps its letter (style §2) and has
no row. The ungated tools (`bench.py`, `profile_delta.py`, `golden_report.py`,
`extract_fixtures.py`, the plots and report of `sweep_jc.py`) take the names of this table
where the same quantity appears (rename-only, ruling 24); they have no rows of their own.

Vocabulary (rulings 1, 15, 26): **node** is a point of half-grid A, **cell** a point of
half-grid B, **grid point** an entry of the interleaved display grid (A0 B0 A1 … AN);
**column** is the whole modelled fluid column; **elbow A** is the elbow the pressure wave
reaches first (force A acts at once; the inlet side of the run), **elbow B** the one it
reaches after the transit delay; the load phases are **transit**, **forced** and **free
decay**; **substep** is one word; **sample** is one entry of the force history; **frame**
is one recorded substep of a trace. The suffix `_a` / `_b` on a fluid quantity means
half-grid A / B; an elbow quantity says `elbow_a` / `elbow_b` in full, so the two never
collide (C-25).

## 1. Fluid column and MoC grid (`moc`, `coupling`)

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `column_cell_count` | N | Cells (half-grid B points) in the whole modelled column: the span, about `L / (2 c dt)` cells, plus `end_to_elbow_cell_count + 1` at each end. The A half-grid has `N + 1` nodes | — | `pipeSegQTY` | `pipe_seg_qty`, `n_seg` (`moc.step`, kernel, `JunctionCoupling`), `N` in prose | R (locals); K (kernel, `JunctionCoupling`); P (`Trace`, `LoopLayout`, exported `pipe_seg_qty`) |
| `end_to_elbow_cell_count` | — | Cells from each end of the column to the elbow at the foot of the leg (the portal-frame pivot): the inactive end cells plus the leg height in cells. Also the index of the A node at elbow A, so `moc.step` reads it as an index | — | `pivotSegQTY` | `pivot_seg_qty`, `pivot` | R (locals); K; P (`Trace`, `LoopLayout`, exported) — see Q-N2 |
| `INACTIVE_END_CELL_COUNT` | — | Cells at each end of the column that receive no mass acceleration (4) | — | `extQTY` | `moc.EXT_QTY`; `ext_qty` (`Trace`, `LoopLayout`, `trace.build` parameter) | R (constant); P (fields, exported `ext_qty`) |
| `grid_point_count` | 2N + 1 | Points of the interleaved display grid | — | — | `n_cells` (`_integrate`, `trace`, `geometry`, `export`) | R (locals); P (`Trace.n_cells`, `LoopLayout.n_cells`, exported `meta.n_cells`) |
| `cell_length` | 2 c dt | Length of one MoC cell (and of one node spacing) | m | — | `cell_length` (`LoopLayout`), `cell_length_m` (exported) | — |
| `grid_point_spacing` | c dt | Distance between neighbouring grid points along the centreline | m | — | `spacing` (`LoopLayout`), `spacing_m` (exported) | P |
| `pressure_a` | p_A | Pressure at the A nodes `0 .. N` | Pa | `arrayA(0, :)` | `p_a` | K |
| `velocity_a` | v_A | Fluid velocity at the A nodes, relative to the pipe | m/s | `arrayA(1, :)` | `v_a` | K |
| `pressure_b` | p_B | Pressure at the B cells `0 .. N-1` | Pa | `arrayB(0, :)` | `p_b` | K |
| `velocity_b` | v_B | Fluid velocity at the B cells, relative to the pipe | m/s | `arrayB(1, :)` | `v_b` | K |
| `moving_fraction_a` | — | Share of the structure's acceleration each A node receives: 0 in the inactive ends, a squared ramp along each leg, 1 along the span (SP-36: "moving fraction" throughout) | — | `interpFractionA(n, …)` | `frac_a` | R (outside kernels); K |
| `moving_fraction_b` | — | The same for the B cells | — | `interpFractionB(n, …)` | `frac_b` | R; K |
| `grid_point_moving_fraction` | — | The two profiles interleaved on the display grid | — | — | `moving_fraction` (`Trace`, `LoopLayout`, exported) | P |
| `fraction_profile` | — | Flag: the moving-fraction profiles of the lead author (`"fixed"`) or of the VBA (`"legacy"`) | — | — | `fraction_profile` | — (public flag; its form changes in the public API session) |
| `characteristic_impedance` (outside kernels); `rho_c` (kernel symbol) | ρc | Fluid density times celerity | Pa·s/m | `rhoC` | `rho_c` | R (locals in `response`); — in kernels; P (exported `rho_c` column) |
| `two_rho_c` (kernel symbol) | 2ρc | `2 * rho_c`, hoisted | Pa·s/m | `(2 * rhoC)` | `two_rho_c` | — |
| `end_pressure_decay_factor` | — | `2 ** (c dt / L)`: the A end-node pressure is the neighbouring B pressure divided by it at every even substep (halving over `2 L / c`) | — | `dacayFactor` | `decay` (`moc.step`, kernel, `JunctionCoupling`, `response`), `su["dacay_factor"]` (tests) | R (locals); K |
| `mean_velocity` | v̄ | Mean of the `2N + 1` fluid velocities, subtracted from every velocity on an even substep | m/s | `vAv` | `v_av` | R (a `moc.step` local) |
| `mean_velocity_divisor` | — | Divisor of the mean-velocity sum: `2N + 1` (fixed) or `2N - 1` (legacy, D-17) | — | `(2 * pipeSegQTY - 1)` | `vav_div` | K |
| `vav_denominator` | — | Flag selecting the divisor | — | — | `vav_denominator` | — (public flag) |
| `junction_force` | ΔF | Force of the fluid column on the structure: the low-pass-filtered flow area × pressure difference across the two elbows (the junction-coupling force) | N | `dF` | `d_f` (`moc.step`, kernel, `JunctionCoupling`, `Trace`, frame column `F_DF`, exported `d_f`) | R (prose); K; P (`Trace.d_f`, exported) |
| `JUNCTION_FORCE_FILTER_WEIGHT` | — | Weight of the previous junction force in its first-order low-pass filter (0.25) | — | `dampingA` | `moc.DAMPING_A` | R |
| `structure_velocity_step` | a dt | The structure's acceleration times the substep: the velocity the moving fraction of the fluid is given | m/s | `a * dt` (in `dv`) | `a_dt` (`moc.step`) | K |
| `is_even_substep` | — | `moc.step` updates the A nodes from the B cells (even) or the B cells from the A nodes (odd) | — | `modDbl(k + (totInd - 1) * stepQTY, 2) = 0` | `even` | K |
| `pressure_b_lower`, `velocity_b_lower` | — | `moc.step`, even half: pressure and velocity of B cell `n - 1`, carried from the previous loop pass | Pa, m/s | `arrayB(0, n - 1)`, `arrayB(1, n - 1)` | `pb_prev`, `vb_prev` | R |
| `pressure_b_upper`, `velocity_b_upper` | — | The same for B cell `n` | Pa, m/s | `arrayB(0, n)`, `arrayB(1, n)` | `pb`, `vb` | R |
| `pressure_a_lower`, `velocity_a_lower` | — | `moc.step`, odd half: A node `n` | Pa, m/s | `arrayA(0, n)`, `arrayA(1, n)` | `pa_prev`, `va_prev` | R |
| `pressure_a_upper`, `velocity_a_upper` | — | The same for A node `n + 1` | Pa, m/s | `arrayA(0, n + 1)`, `arrayA(1, n + 1)` | `pa`, `va` | R |
| `flow_area` | A | Internal cross-sectional area of the pipe (the pressure area) | m² | `fluidArea` | `fluid_area`; `fluid_area_m2` (exported) | R (locals); K; P (public keyword, exported; parameters of non-underscore functions: Q-N1) |
| `fluid_density` | ρ | Fluid density | kg/m³ | `fluidDensty` | `fluid_densty` | P (public keyword; the frozen fixtures keep the VBA key, K-9 of R.2) |
| `celerity` | c | Pressure-wave speed in the pipe; also the speed the force travels between the elbows | m/s | `celerity` | `celerity` | — |
| `is_short_pipe` | — | The span cannot hold the MoC grid; the JC solver falls back to the lumped one | — | `pipeSegQTY - 2 * pivotSegQTY <= 2` | `moc.is_short_pipe()`; `jc_short_pipe` (exported column) | — (function); P (column) |

## 2. Structure (`structure`)

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `x` (kernel symbol); `displacement` elsewhere | x | Displacement of the SDOF proxy | m | `x` | `x` | — in kernels; P (`Trace.x`, exported `x`) |
| `v` (kernel symbol); `velocity` elsewhere | v | Velocity of the proxy | m/s | `v` | `v` | as `x` |
| `a` (kernel symbol); `acceleration` elsewhere | a | Acceleration of the proxy | m/s² | `a` | `a` | as `x` |
| `v_new`, `a_new` (kernel symbols) | — | Velocity and acceleration at the end of the substep | m/s, m/s² | `vNew`, `aNew` | `v_new`, `a_new` | — |
| `dt` (kernel symbol); `substep_duration` elsewhere | Δt | One substep: `1 / (sample_rate * substep_count)` | s | `dt` | `dt`, `time_step` (prose) | — in kernels; R (locals and non-public parameters elsewhere); P (`Trace.dt`, exported `params.dt`) |
| `half_dt` (kernel symbol) | Δt/2 | `dt / 2` | s | — | `half_dt` | — |
| `mass` | m | Modal mass of the proxy: lumped `(L + 4h/3) m'`; JC the rigid mass, core fluid removed | kg | `mass` | `SdofParams.mass`, `mass` | — |
| `stiffness` | k | Lateral stiffness with the support gaps open | N/m | `stiffness` | `SdofParams.stiffness` | — |
| `damping` | c_d | Viscous damping coefficient | N·s/m | `damping` | `SdofParams.damping` | — |
| `friction_velocity_step` | — | Velocity Coulomb friction removes per substep: `0.5 μ g dt` (lumped; JC × total / rigid mass) | m/s | `fricAcc` | `SdofParams.fric_acc`, `fric_acc`; `params.fric_acc` (exported) | R (field, locals); K (`step_scalars` parameter); P (exported key) |
| `support_gap` | — | Gap at the supports, at the centre of mass, before the closed-gap stiffness acts | m | `gap` | `SdofParams.gap`, `gap` | R (field, locals); K; P (public keyword, exported) |
| `closed_gap_stiffness_ratio` | (f_c/f_o)² | Stiffness beyond the gap over the open-gap stiffness: `restrain_freq_ratio ** 2` | — | `restrainFreqRatio ^ 2` | `SdofParams.ratio2`, `ratio2`; `params.ratio2` (exported) | R; K; P (exported) |
| `closed_gap_frequency_ratio` | — | Natural frequency with the gaps closed over that with them open | — | `restrainFreqRatio` | `restrain_freq_ratio` | P (public keyword) |
| `external_force` | F | Force on the proxy from the loads: unbalance plus junction force in the forced phases, junction force alone in free decay | N | `forceA - forceB + dF` (inline) | `f_applied` | K (kernel local and `step_scalars` parameter) |
| `x_magnitude` | \|x\| | `abs(x)` in the gap ladder | m | `Abs(x)` | `ax` (`step_scalars`, `effective_displacement`) | R |
| `x_within_gap` | — | Displacement up to the gap, signed: `minUnsigned(gap, x)` | m | `minUnsigned(gap, x)` | `clamp` | R |
| `x_excess_magnitude` | — | `max(0, abs(x) - gap)` | m | `max(0, Abs(x) - gap)` | `excess` | R |
| `x_beyond_gap` | — | The same with the sign of `x` | m | `max(…) * sign(x)` | `beyond` | R |
| `trapezoid_velocity_change` | — | `(a + a_new) * dt / 2` | m/s | `(a + aNew) * dt / 2` | `av` | R |
| `effective_displacement` | — | Displacement the open-gap stiffness sees: `x_within_gap + x_beyond_gap * closed_gap_stiffness_ratio` | m | (inline, lines 424, 611) | `effective_displacement()` | — |
| `portal_frame_height` | h | Height of the legs of the portal-frame proxy that give the natural frequency | m | `portalFrameHeight` | `portal_frame_height`, `h` (`response`, `geometry`, tools), `height` (`sweep_jc`); `portal_height` (`LoopLayout`), `portal_height_m` (exported) | R (`h` locals); P (`LoopLayout`, exported) |
| `span_length` | L | Length between the elbows (the span the proxy models) | m | `physicalLength` | `physical_length`; `length_m` (CSV, `Case`) | R (locals); P (public keyword, `trace.inputs` key, column) |
| `flexural_rigidity` | EI | Flexural rigidity of the pipe | N·m² | `flexuralRigidityEI` | `flexural_rigidity_ei`; `ei` (`Pipe`, column) | R (`Pipe` field); P (keyword, column) |
| `mass_per_length` | m' | Mass per unit length, pipe and contents | kg/m | `massPerUnitLen` | `mass_per_unit_len`; `mass` (`sweep_jc.pipe`) | R (locals); P (keyword, column; frozen fixtures keep the old key) |
| `natural_frequency` | f_n | Natural frequency with the gaps open (JC: modelled with the fluid included) | Hz | `natFreq` | `nat_freq`; `nat_freq_hz` (`Case`, column) | P |
| `damping_percent` | ζ | Damping as a percentage of critical | % | `dampingPercent` | `damping_percent` | — |
| `friction_coefficient` | μ | Coulomb friction coefficient | — | `dynamicFric` | `dynamic_fric`; `mu` (`Case`, column, tools) | R (`Case.mu`); P (keyword, column) |
| `omega_squared` | ω² | `(2 π f_n)²` | rad²/s² | `(2 * pi * natFreq) ^ 2` | `omega2` (`solve_portal_height`) | R |
| `GRAVITY` | g | 9.81, fixing m and s in the friction step (style §6; plan 2.5 names it, not here) | m/s² | `9.81` | literal | — (plan 2.5) |
| `VBA_PI` | π | The VBA's 15-digit π | — | `Const pi` | `VBA_PI` | — |
| `quartic_constant`, `cubic_coefficient`, `quartic_coefficient` | — | Coefficients of `c0 + c3 L³ + c4 L⁴ = 0`, the portal-height equation (`kg·m³`, kg, kg/m in that use) | see meaning | `varA`, `varB`, `varC` | `var_a`, `var_b`, `var_c` | P (parameters of `solve_poly`); R (`var_b`, `var_c` locals in `solve_portal_height`) |
| `root` | — | The Newton iterate, the portal height in its one use | m | `lenVal` | `len_val` | R |
| `residual` | — | Value of the polynomial at the iterate | kg·m³ | `errorVal` | `error_val` | R |
| `slope` | — | Derivative of the polynomial at the iterate | kg·m² | `grad` | `grad` | R |
| `NEWTON_RELAXATION` | — | Under-relaxation of the Newton step (0.25; a module constant in plan 2.5, named here) | — | `Const relax` | `relax` | R |

## 3. Loads and the schedule walk (`loads`)

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `force_history` | — | The force-time history at one location, as given (1-D, or 2-D walked column-major) | N | `forceHistory` | `force_history` (keyword), `history` (`response` local, `loads` parameters), `force` (tools) | R (locals and `loads` parameters, see Q-N1); — (public keyword) |
| `force_history_one_based` | — | The history as 1-based nested lists, `[row][column]` (`vba_2d`) | N | `forceHistory(i, j)` | `fh` (`_Run`) | R |
| `history_row_count`, `history_column_count` | — | Rows and columns of the 2-D history | — | `UBound(forceHistory, 1)`, `UBound(forceHistory, 2)` | `u1`, `u2` | R |
| `substep_count` | — | Substeps per sample | — | `stepQTY` | `step_qty`; `STEP_QTY` (`sweep_jc`); `params.step_qty` (exported) | R (`_Run` field, locals, `STEP_QTY` → `SUBSTEP_COUNT`); K; P (keyword, `Trace.step_qty`, exported) |
| `sample_rate` | f_s | Sample rate of the force history | Hz | `sampleFreq` | `sample_freq`; `SAMPLE_FREQ`, `DEFAULT_SAMPLE_FREQ` | R (constants); P (keyword, `History`, column) |
| `transit_delay_samples` | L f_s / c | Time the force takes from elbow A to elbow B, in samples (fractional) | samples | `unballanceStepQTY` | `unb` (`_Run`, `response`, tools), `unballance_step_qty` (`overlap_substeps` parameter), `transit_delay()` return | R |
| `transit_delay_substeps` | — | The same in substeps: `transit_delay_samples * substep_count` (a float threshold) | substeps | `unballanceStepQTY * stepQTY` | `unb_steps` (`_Run`) | R |
| `overlap_substep_count` | — | Fractional part of the transit delay in substeps, rounded: elbow B runs this many substeps ahead of the sample boundary | — | `kOverlap` | `k_overlap` | R |
| `next_sample_weight` | — | Ramp weight of the next sample, `k / (substep_count - 1)` for `k = 0 .. substep_count - 1` | — | `k / (stepQTY - 1)` | `frac` (`_Run`) | R |
| `current_sample_weight` | — | `1 - next_sample_weight` | — | `1 - k / (stepQTY - 1)` | `one_minus` (`_Run`) | R |
| `elbow_a_force` | F_A | Force at elbow A | N | `forceA` | `force_a` (`_schedule`, generators), `fa` (lists), `f_a` (`Trace`, `_trace_frame`), `F_FA` | R (loads); K (kernel); P (`Trace.f_a`, exported `f_a`) |
| `elbow_b_force` | F_B | Force at elbow B, delayed by the transit | N | `forceB` | `force_b`, `fb`, `f_b`, `F_FB` | as above |
| `unbalance_force` | F_A − F_B | Force on the span from the two elbows | N | `forceA - forceB` | `f` (kernel), `f_u` (`_trace_frame`), `f_unbalance` (`Trace`, exported), `flat` (array), `forces` (generator), `samples`, `sample` (lists), `F_FU` | R (loads, `_integrate` locals); K; P |
| `elbow_a_force_current`, `elbow_a_force_next` | — | Forced phase: the two history values elbow A's ramp runs between | N | `forceHistory(i, j)`, `forceHistory(imax, jmax)` | `fa_cur`, `fa_nxt` | R |
| `elbow_b_force_current`, `elbow_b_force_next` | — | The pair elbow B ramps between (transit phase; forced phase before it advances) | N | `forceHistory(iB, jB)`, `forceHistory(iBmax, jBmax)` | `f_cur`, `f_nxt` (transit items), `fb_cur`, `fb_nxt` | R |
| `elbow_b_force_advanced_current`, `elbow_b_force_advanced_next` | — | Forced phase: elbow B's pair after it advances one sample, for the last `overlap_substep_count` substeps of the sample | N | the same, after the advance | `fb2_cur`, `fb2_nxt` | R |
| `history_row`, `history_column` | — | Position in the history of the sample elbow A reads (transit phase: elbow B's, clamped) | — | `i`, `j` | `i`, `j` (`_schedule`) | R (they live over 40 lines) |
| `next_history_row`, `next_history_column` | — | The sample after it, wrapping to the next column | — | `imax`, `jmax` | `imax`, `jmax` | R |
| `elbow_b_row`, `elbow_b_column` | — | Position in the history of the sample elbow B reads | — | `iB`, `jB` | `ib`, `jb` | R |
| `elbow_b_next_row`, `elbow_b_next_column` | — | The sample after it | — | `iBmax`, `jBmax` | `ibmax`, `jbmax` | R |
| `transit_last_column` | — | Upper bound of the column loop of the transit walk: `1 + CLng(transit_delay_samples / history_column_count)` | — | `1 + CLng(unballanceStepQTY / UBound(forceHistory, 2))` | `jb_to` | R — see Q-N3 |
| `sample_number` | — | 1-based number of the sample being walked or integrated (samples begun so far); the 0-based sample index is `sample_number - 1` | — | `totInd` | `tot_ind` (`_schedule`, generators, kernel) | R (loads); K (kernel) |
| `first_substep_number` | — | 1-based running number of the sample's first substep, `(sample_number - 1) * substep_count + 1`, tested against `transit_delay_substeps` | — | `(totInd - 1) * stepQTY + 1` | `base` | R |
| `pre_advance_substep_count` | — | Substeps of a forced sample before elbow B advances: `substep_count - overlap_substep_count` | — | `stepQTY - kOverlap` | `split` | R |
| `advanced_ramp_index` | — | Ramp index of elbow B after it advances, `k - substep_count + overlap_substep_count` | — | `k - stepQTY + kOverlap` | `m` | R |
| `sample_forces`, `elbow_a_forces`, `elbow_b_forces` | — | The per-substep values of one sample, as yielded | N | — | `sample`, `fa`, `fb` | R |
| `walk` | — | The per-run constants of the walk (`_Run`) | — | — | `run` | R |
| `PHASE_TRANSIT`, `PHASE_FORCED`, `PHASE_FREE_DECAY` | — | Load-phase labels 0 / 1 / 2: elbow A loaded and elbow B still waiting (transit); both elbows driven by the history (forced); no load (free decay) | — | (the three loops) | `PHASE_TRANSIT`, `PHASE_HISTORY`, `PHASE_FREE_DECAY`; bare `0` / `1` tags in `loads`; "delay" / "ramp" / "history" in prose | R (constants and prose; plan 2.1 moves them, plan 1.4 renames) |
| `load_phase` | — | The phase of a sample or frame | — | — | `phase`, `_phase`, `ph` | R (locals); K; P (`Trace.phase`, exported `phase`) |

## 4. Run bookkeeping and the kernel (`response`)

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `nominal_forced_sample_count` | — | History samples plus the rounded transit delay: the samples the forced phases take, as the VBA sizes its result | — | `outMax` | `out_max`; `Trace.out_max`; `params.out_max` (exported) | R (`response` locals); K; P (field, exported) — see Q-N4 |
| `recorded_sample_count` | — | `2 * nominal_forced_sample_count`: the samples the response history and the trace keep (the forced samples and an equal allowance for free decay; precomputing it is allowed, ruling 25) | — | `outMax * 2` | `out_max * 2` (inline, five sites) | K (plan 4.5) |
| `forced_sample_count` | — | Samples of the transit and forced phases, as integrated | — | `totInd` after phase 2 | `n_samples` and `forced_samples` (kernel; the same value), `len(samples)` (`_integrate`), `forced_samples` (`trace.capacity`) | K (kernel); R (`trace`) — see Q-N5 |
| `forced_substep_count` | — | Substeps of the transit and forced phases | — | — | `n_sub` (`_integrate`), `forced_substeps` (`trace`, `tools/cases.py`) | R |
| `transit_substep_count` | — | Substeps of the transit phase, counted from the elbow-force walk | — | — | `delay_substeps` | K |
| `free_decay_sample_count` | — | Samples integrated in free decay | — | — | `PeakResponse.free_decay_samples`, `free_decay_samples` (exported) | P |
| `substep_index` | n | Running 0-based substep counter over the whole run; its parity (or that of `+ parity_offset`) picks the MoC half-grid | — | `k + (totInd - 1) * stepQTY` | `n` (kernel), `step_index` (prose), `sub_step` (`Trace`, exported), `I_SUB_STEP` | K; P (`Trace.sub_step`, exported) |
| `parity_offset` | — | Added to `substep_index` for the VBA per-phase parity (D-19); 0 for the running parity | — | — | `off` | K |
| `is_per_phase_parity` | — | The per-phase parity flag as a boolean for the kernel | — | — | `legacy_parity` | K |
| `is_fluid_coupled` | — | Fluid coupling on (JC) or off (lumped), the plain flag of plan 2.2 | — | — | `kind` (0 / 1), `JunctionCoupling.KIND` (removed in R.3) | K (plan 2.2) |
| `unbalance_force_by_substep` | — | The per-substep unbalance forces of the forced phases, flattened | N | — | `flat` | K |
| `sample_start` | — | Index into `unbalance_force_by_substep` of each sample's first substep (length samples + 1) | — | — | `offsets` | K |
| `elbow_a_force_by_substep`, `elbow_b_force_by_substep` | — | The elbow forces, flattened the same way (trace only) | N | — | `flat_a`, `flat_b` | K |
| `unbalance_force_samples` | — | The per-sample lists of `loads.unbalance_force`, as `_integrate` receives them | N | — | `forces` (parameter), `samples` (list) | R |
| `elbow_force_samples` | — | The per-sample `(phase, elbow A, elbow B)` items of `loads.elbow_forces` | N | — | `elbows`, `_TraceMeta.elbows` | R |
| `response_history` | — | Displacement / velocity / acceleration at the end of each sample, for `output_type` 1 / 2 / 3 | m, m/s, m/s² | `resultArray` | `history` (`_integrate`, kernel, `_record`); `PeakResponse.history` | R (`_integrate`); K; P (`PeakResponse.history`) |
| `output_type` | — | 0: maxima only; 1 / 2 / 3: also the displacement / velocity / acceleration history | — | `outputType` | `output_type` | — (its form changes in the public API session) |
| `x_max`, `v_max`, `a_max` (kernel symbols) | — | Largest `abs(x)`, `abs(v)`, `abs(a)` | m, m/s, m/s² | `xMax`, `vMax`, `aMax` | the same | — |
| `unbalance_force_max` | — | Largest `abs(unbalance_force)` of the forced phases | N | `FMax` | `f_max` (kernel); `PeakResponse.max_applied_force`, exported `max_applied_force` | K; P (`max_unbalance_force`; frozen fixtures keep the old key) |
| `static_equivalent_force_max` | F_eq | `abs(effective_displacement(x_max)) * stiffness` | N | `resultArray(0)` | `static_equivalent` (`_integrate`); `PeakResponse.max_static_equivalent_force` | R (local); — (field) |
| `decay_start_displacement` | — | Displacement at the start of free decay; set to 0 to end the loop once `x * it <= 0.01` | m | `xZero` | `x_zero` | K |
| `free_decay_product` | — | `x * decay_start_displacement`, the free-decay test (D-21) | m² | `x * xZero` | `p` (`_decay_test`) | R |
| `v_before`, `a_before` (kernel symbols) | — | Velocity and acceleration before the substep, kept for the traced friction force | m/s, m/s² | — | `v_old`, `a_old` | K |
| `record_frame` | — | The substep is traced (style §2's own example) | — | — | `rec` | K |
| `frame_capacity` | — | Frames the trace buffers hold | — | — | `cap` (kernel, `_integrate`, `trace`), `capacity()` return | R (`trace`, `_integrate`); K |
| `frame_count` | — | Frames written so far, also the next frame's row | — | — | `frame` (kernel), `n_frames` (kernel return, `trace.build`, `Trace.n_frames`) | K; P (`Trace.n_frames`, exported `meta.n_frames`) |
| `frame_index` | — | Row to write in `_trace_frame` | — | — | `frame` (`_trace_frame` parameter) | K |
| `sample_index` | — | 0-based sample index (`sample_number - 1`) | — | `totInd - 1` | `sample` (`_trace_frame`, `Trace`, exported), `index` (`_record`) | K (`_trace_frame` and `_record` are compiled); P (`Trace.sample`, exported `sample`) |
| `friction_force` | — | Force the Coulomb branch applied in the substep, recomputed for the trace | N | — | `f_fric`, `f_friction`, `F_FFRIC` | K; P (`Trace.f_friction`, exported) |
| `is_sticking` | — | The substep took the stick branch (`abs(v_before) < friction_velocity_step`) | — | `Abs(v) < fricAcc` | `stick`, `I_STICK` | K; P (`Trace.stick`, exported) |
| `sdof_params` | — | The `SdofParams` of the run | — | — | `params`, `p` (`export`) | R (locals) |
| `junction_coupling` | — | The `JunctionCoupling` of a JC run, `None` for lumped | — | — | `junction` (`peak_response_jc`), `coupling`, `jc` (`_integrate`, `trace.build`) | R (locals); K (`trace.build`'s `jc`, replaced by the grid description of plan 3.6) |
| `trace_request` | — | What `_integrate` needs beyond the kernel arrays to build a `Trace` (`_TraceMeta`) | — | — | `meta` | R |
| `_TraceMeta.solver`, `.inputs`, `.celerity` | — | Solver name; the inputs echo; the pressure-wave speed | —, —, m/s | — | the same | — |
| `_TraceMeta.elbow_force_samples` | — | See above | N | — | `_TraceMeta.elbows` | R |
| `trace_every` | — | Trace stride in substeps (0: no trace) | — | — | `trace_every` | — (public keyword) |
| `column_arrays`, `column_scalars` | — | The tuples the column is passed to the kernel as (they go with the column NamedTuple, plan 3.2) | — | — | `column`, `scalars` | K |
| `no_column` | — | The empty array the lumped run passes for every column array | — | — | `empty` | K |

## 5. Trace (`trace`)

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `frame_state` | — | Per-frame float columns: `x, v, a`, the three loads, the friction and junction forces (`frame_capacity × 8`) | mixed | — | `tr_f`, `f` (`build`) | K (kernel); R (`build` local) |
| `frame_index_columns` | — | Per-frame int columns: substep, sample, phase, stick (`frame_capacity × 4`) | — | — | `tr_i`, `ints` | K; R |
| `frame_pressure`, `frame_velocity` | — | Per-frame interleaved grid-point pressures and velocities (`frame_capacity × grid_point_count`) | Pa, m/s | — | `tr_p`, `tr_v` | K |
| `COL_X`, `COL_V`, `COL_A`, `COL_ELBOW_A_FORCE`, `COL_ELBOW_B_FORCE`, `COL_UNBALANCE_FORCE`, `COL_FRICTION_FORCE`, `COL_JUNCTION_FORCE` | — | Column positions in `frame_state` | — | — | `F_X`, `F_V`, `F_A`, `F_FA`, `F_FB`, `F_FU`, `F_FFRIC`, `F_DF` | R (constants; the kernel picks them up at compile time: cache wipe) |
| `COL_SUBSTEP_INDEX`, `COL_SAMPLE_INDEX`, `COL_LOAD_PHASE`, `COL_IS_STICKING` | — | Column positions in `frame_index_columns` | — | — | `I_SUB_STEP`, `I_SAMPLE`, `I_PHASE`, `I_STICK` | R |
| `FRAME_STATE_COLUMN_COUNT`, `FRAME_INDEX_COLUMN_COUNT` | — | 8 and 4 | — | — | `N_FLOAT_COLUMNS`, `N_INT_COLUMNS` | R |
| `MAX_TRACE_VALUES` | — | Memory guard: largest number of 8-byte values a trace may allocate | — | — | `MAX_TRACE_VALUES` | — |
| `values_per_frame` | — | 8-byte values one frame needs | — | — | `per_frame` | R |
| `fitting_stride` | — | Smallest stride whose trace fits the guard, for the message | — | — | `stride` | R |
| `allocated_grid_point_count` | — | Grid-point columns allocated (0 when no frame) | — | — | `cells` (`allocate`) | R |
| `time` | t | Time at the end of the frame's substep, `(substep_index + 1) * dt` | s | — | `Trace.t`, exported `t` | P |
| `grid_point_pressure`, `grid_point_velocity` | — | Per frame, the interleaved column | Pa, m/s | — | `Trace.p_cells`, `Trace.v_cells`; exported `cells.p`, `cells.v` | P |
| `grid_point_position` | — | Position along the column from the first A node, `j * c * dt` | m | — | `cell_position` (`Trace`, `LoopLayout`), `cell_position_m` (exported), `position` (`geometry`) | R (locals); P |
| `grid_point_kind` | — | 0 for an A node, 1 for a B cell | — | — | `cell_kind`, `kind` (`geometry` local) | R (local); P |
| `solver` | — | `"peak_response"` or `"peak_response_jc"` | — | — | `Trace.solver` | — |
| `inputs` | — | The case inputs as the solver received them | — | — | `Trace.inputs` | — |

## 6. Loop layout (`viz/geometry`)

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `inlet_elbow_index` | — | Grid point of the elbow between the inlet and leg 1 (last fraction-0 point before the span) | — | — | `inlet_end` (`LoopLayout`, `segments.inlet_end`) | P |
| `run_start_index`, `run_end_index` | — | First and last fraction-1 grid points: the two elbows at the feet of the legs, the ends of the run | — | — | `run_start`, `run_end` | P — see Q-N6 |
| `outlet_elbow_index` | — | Grid point of the elbow between leg 2 and the outlet | — | — | `outlet_start` | P |
| `elbow_grid_point_pairs` | — | The two grid points either side of each of the four drawn elbows | — | — | `elbow_pairs` | P |
| `x_at_rest`, `y_at_rest` | — | Circle centres at rest on the loop | m | — | `x_nominal`, `y_nominal`; exported `x_nominal_m`, `y_nominal_m` | P |
| `run_length` | — | Centreline length of the run | m | — | `run_length` | — |
| `inlet_leg_height`, `outlet_leg_height` | — | Height of the inlet and outlet pipes above the run (SP-35) | m | — | `leg_height`, `leg_height_2`, `height1`, `height2` | R (locals); P (fields, exported) |
| `centreline_position` | s | Grid-point positions as `loop_layout` lays them | m | — | `s` | R |
| `inlet_elbow_position`, `run_start_position`, `run_end_position`, `outlet_elbow_position` | — | `centreline_position` at the four elbows | m | — | `s1`, `s2`, `s3`, `s4` | R |
| `on_inlet`, `on_inlet_leg`, `on_run`, `on_outlet_leg`, `on_outlet` | — | Masks of the grid points on each piece of the loop | — | — | `inlet`, `leg1`, `run`, `leg2`, `outlet` | R |
| `fully_moving`, `still_before_run`, `still_after_run` | — | Indices of fraction-1 points; fraction-0 points before and after the run | — | — | `ones`, `before`, `after` | R |

## 7. Exported documents (`export`)

Exported keys change only at the schema bump (P); the internal names here are R.

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `is_junction_coupled` | — | The trace is a JC trace (it has grid-point arrays) | — | — | `jc` (`to_trace_dict`) | R |
| `in_free_decay` | — | Mask of the free-decay frames | — | — | `decay` (`is_capped`) | R |
| `is_capped` | — | The run decayed past the recorded window, so the trace ends early | — | — | `is_capped()`, exported `params.capped` | — (function); P (key) |
| `rest_frame` | — | The synthetic `t = 0` frame's values | — | — | `rest` | R |
| `frame_values` | — | One column with the rest frame first | — | — | `traced`, `first`, `full` | R |
| `TRACE_SCHEMA_VERSION` | — | `schema_version` of a trace document | — | — | `SCHEMA_VERSION` | — (S-N15 was rejected; listed for the bump) |
| `location` | — | The JSON path a value sits at, for messages | — | — | `where` | — |

## 8. Pressure histories (`histories`)

`canonical`, `from_params` and `p_cap` are user-facing entry points (rulings 4, 18): their
names and parameters change in the public API session. `History` is returned to users (P).

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `history_type` | — | `"step"`, `"step_sine"` or `"step_noise"` | — | — | `History.kind`, `kind`, `KINDS`; column `history_type` | R (`KINDS` → `HISTORY_TYPES`); P (field, parameter) |
| `time` | t | Sample times, `arange(n) / sample_rate` | s | — | `History.time`, `time` | — |
| `pressure` | p | Pressure | Pa | — | `History.pressure` | — |
| `lead_in_s`, `transit_s`, `tail_s`, `decay_s`, `duration_s` | — | The four duration terms and their sum | s | — | the same | — |
| `step_pressure` | — | Held step pressure | Pa | — | `p_step` | P |
| `oscillation_amplitude`, `oscillation_frequency` | — | Sine amplitude before the envelope; its frequency (`step_sine`) | Pa, Hz | — | `p_osc`, `f_osc`; column `f_osc_hz` | P |
| `requested_noise_rms` | — | White-noise RMS asked for (inert after the peak scaling) | Pa | — | `p_noise_rms` | P |
| `noise_cutoff_frequency` | — | Low-pass cut-off of the noise | Hz | — | `f_cut`; column `f_cut_hz` | P |
| `envelope_reference_frequency` | — | Frequency whose cycles set the noise envelope | Hz | — | `f_ref`; `F_REF_NOISE` (`sweep_jc`) | P; R (`NOISE_REFERENCE_FREQUENCY`) |
| `noise_seed` | — | RNG seed | — | — | `seed` | P |
| `envelope_decay_cycles`, `envelope_decay_fraction` | — | The envelope falls by the fraction after this many cycles | —, — | — | `decay_cycles`, `decay_fraction` | P |
| `peak_pressure_target` | p_cap | `amplitude_fraction * PEAK_TO_DESIGN_PRESSURE_RATIO * design_pressure` | Pa | — | `p_cap` (field, function, parameter), `cap` (`canonical` local) | R (`cap`); P |
| `PEAK_TO_DESIGN_PRESSURE_RATIO` | — | 1.33 (ruling 27) | — | — | `P_CAP_FACTOR` | R |
| `design_pressure` | — | Hoop-stress design pressure `2 t S / OD` | Pa | — | `p_design` (`canonical`, `p_cap`, `Pipe`) | R (`Pipe`); P |
| `amplitude_fraction` | — | Peak as a fraction of the cap | — | — | `amplitude_fraction` | — |
| `sample_count` | — | Samples of the history | — | — | `n_samples`, `n` (`_axis`) | R (`n`); P (field, column) |
| `lead_in_sample_count` | — | Zero samples before the step | — | — | `n_lead` (also `tools/cases.py`) | R |
| `pressure_max`, `pressure_min`, `pressure_mean`, `pressure_rms` | — | Statistics of the whole history | Pa | — | `peak`, `p_min`, `mean`, `rms` | P |
| `scaled_noise_rms` | — | RMS of the scaled noise over the active window | Pa | — | `noise_rms` | P |
| `time_since_lead_in` | τ | Time from the end of the lead-in | s | — | `tau` | R |
| `unit_sine` | — | The enveloped unit sine | — | — | `u` | R |
| `noise` | — | The noise before scaling (raw, filtered, enveloped) | Pa | — | `w` | R |
| `noise_max` | — | Its maximum | Pa | — | `w_max` | R |
| `scaled_noise` | — | The noise scaled to reach the target | Pa | — | `noise` | R |
| `frequency` | f | Frequency argument of `decay_rate` / `envelope` | Hz | — | `f` | R (`decay_rate`, `envelope` are not tool-called; see Q-N1) |
| `shared_arguments` | — | Keyword arguments common to the generators | — | — | `common` | R |
| `unit_sine_history` | — | The unit-amplitude probe that sizes the sine | — | — | `probe` | R |
| `HISTORY_TYPES`, `DEFAULT_SAMPLE_RATE` | — | Constants | — | — | `KINDS`, `DEFAULT_SAMPLE_FREQ` | R |

## 9. Tools (`tools/sweep_jc.py` run part, `tools/cases.py`)

Column names and argparse flag strings are exported or pinned and stay; argparse `dest`
names and locals are R.

| proposed | symbol | meaning | unit | VBA | current | when |
|---|---|---|---|---|---|---|
| `Pipe.outside_diameter_mm`, `Pipe.wall_thickness_mm` | OD, t | Pipe dimensions | mm | — | `od_mm`, `thk_mm` | R (fields; columns `od_mm`, `thk_mm`: P) |
| `Pipe.flow_area`, `.mass_per_length`, `.flexural_rigidity`, `.design_pressure` | — | As above | m², kg/m, N·m², Pa | — | `fluid_area`, `mass_per_unit_len`, `ei`, `p_design` | R |
| `inside_radius`, `outside_radius` | — | Pipe radii | m | — | `r_in`, `r_out` | R |
| `second_moment_of_area` | I | Of the pipe wall | m⁴ | — | `inertia` | R |
| `FLUID_DENSITY`, `PIPE_DENSITY` | ρ | 1000, 7800 | kg/m³ | — | `RHO_FLUID`, `RHO_PIPE` | R |
| `PA_PER_BAR` | — | 1e5 (the factor converts bar to Pa) | Pa/bar | — | `BAR` | R |
| `SUBSTEP_COUNT`, `SAMPLE_RATE`, `CLOSED_GAP_FREQUENCY_RATIO`, `SUPPORT_GAP` | — | Fixed sweep inputs | —, Hz, —, m | — | `STEP_QTY`, `SAMPLE_FREQ`, `RESTRAIN_FREQ_RATIO`, `GAP` | R |
| `Case.natural_frequency`, `Case.friction_coefficient` | — | As above | Hz, — | — | `nat_freq_hz`, `mu` | R (fields; the columns stay until P) |
| `pipe_properties` | — | The `Pipe` of the case | — | — | `p` (`run_case`) | R |
| `pressure_history` | — | The `History` of the case | — | — | `h` (`run_case`) | R |
| `total_mass` | — | `(L + 4h/3) m'`, pipe and contents | kg | — | `mass_total`; column `mass_total_kg` | R |
| `outside_diameter_squared` | D² | `(OD / 1000)²` | m² | — | `d2` | R |
| `peak_pressure_force` | — | Peak pressure times flow area, the reference of the amplification factor | N | — | `p_peak_a` | R |
| `lumped_result`, `jc_result`, `result` | — | The two solver results | — | — | `lumped`, `jc`, `r` | R |
| `solver_arguments` | — | The solver keyword arguments | — | — | `kw` (`run_case`, `cases.py`) | R |
| `diameter_mm`, `amplitude_bar`, `lead_in_s`, `duration_s`, `fluid_density` (argparse `dest`) | — | Step-case options; the flag strings stay | mm, bar, s, s, kg/m³ | — | `size`, `amplitude`, `lead_in`, `duration`, `density` | R |
| `hold_sample_count` | — | Samples the step is held | — | — | `n_hold` | R |
| `dynamic_amplification_factor_*` | DAF | `F_eq / peak_pressure_force` | — | — | column `daf_*` | P |
| `static_force_per_length_diameter_squared_*` | — | `F_eq / (L D²)` | N/m³ | — | column `f_eq_over_LD2_*` | P |

## 10. Function names

| proposed | current | meaning | when |
|---|---|---|---|
| `moving_fraction_a`, `moving_fraction_b`, `moving_fraction_a_fixed`, `moving_fraction_b_fixed`, `moving_fractions` | `moc.interp_fraction_a`, `_b`, `_a_fixed`, `_b_fixed`, `interp_fractions` | The moving-fraction profiles (SP-36) | P (public by Python convention; R if Q-N1 is answered "style §2's sense") |
| `column_at_rest` | `moc.new_column` | The four column arrays at rest | P / R (Q-N1) |
| `mean_velocity_divisor` | `moc.vav_divisor` | | P / R |
| `end_pressure_decay_factor` | `moc.decay_factor` | | P / R |
| `solve_quartic` | `structure.solve_poly` | Relaxed Newton root of `c0 + c3 L³ + c4 L⁴` | P / R |
| `_free_decay_product` | `response._decay_test` | `x * x_zero` with the overflow check | R |
| `_record_sample` | `response._record` | Store the end-of-sample state in the response history | R |
| `_walk_constants` | `loads._run` | Per-run constants of the walk | R |
| `allocate_frames`, `frame_capacity`, `build_trace` | `trace.allocate`, `trace.capacity`, `trace.build` | | P / R |
| `_moving_fractions_display` | `geometry._interp_fractions_display` | | R |
| `peak_pressure_target` | `histories.p_cap` | | P (tool-called, ruling 18) |
| `step` (unchanged) | `moc.step` | Split into the two half-grid updates in plan 4.2, which names them | — |

## Kernel symbols (style §2)

Licensed inside the compiled kernels (`moc.step`, `structure.step_scalars`,
`response._integrate_kernel`, `response._trace_frame`, `response._record`,
`response._decay_test`) and, from plan group 3, in their positional signatures. Nowhere
else.

| symbol | meaning | unit |
|---|---|---|
| `x`, `v`, `a` | Displacement, velocity, acceleration of the SDOF proxy | m, m/s, m/s² |
| `v_new`, `a_new` | Their values at the end of the substep | m/s, m/s² |
| `v_before`, `a_before` | Their values before the substep (trace) | m/s, m/s² |
| `x_max`, `v_max`, `a_max` | Largest magnitudes so far | m, m/s, m/s² |
| `dt`, `half_dt` | Substep duration and half of it | s |
| `rho_c`, `two_rho_c` | Characteristic impedance ρc and 2ρc | Pa·s/m |
| `n` | Loop index over nodes or cells in `moc.step` (a few lines each) | — |

## Questions for the owner

* **Q-N1. Which functions are "public" for this session?** The brief says public function
  names and their parameters wait for the public API session. By Python convention that is
  every function without a leading underscore; by `docs/style.md` §2 only the user-facing
  entry points (`response` solvers, `histories.canonical`, `from_params`, `p_cap`, the
  `export.to_*_dict` functions) are public. The "when" column takes the first reading
  (P). Under the second, the functions of section 10 marked "P / R" and the parameters of
  `structure.lumped_params`, `jc_params`, `solve_poly`, `loads.*`, `moc.*`, `trace.*` and
  `JunctionCoupling.__init__` would be renamed now.
* **Q-N2. `pivotSegQTY`.** I read it as the cells from each end of the column to the elbow
  at the foot of the leg (end cells plus the leg height in cells), so the junction force
  taps the pressure at the two elbows, and the "pivot" is that elbow. Is the portal-frame
  pivot the elbow between leg and span? If not, `end_to_elbow_cell_count` is wrong.
* **Q-N3. `jb_to`.** `1 + CLng(unballanceStepQTY / UBound(forceHistory, 2))` divides the
  transit delay in samples by the number of *columns*; the samples per column are the
  rows. The walk exits on `totInd > unballanceStepQTY` before the bound matters in every
  case the tests run. I named it for what it is (`transit_last_column`); is it meant as a
  bound on columns, or is the divisor a VBA slip (a question for the lead author, not a
  change)?
* **Q-N4. `outMax`.** Proposed `nominal_forced_sample_count` (history samples plus the
  rounded transit delay). The forced phases actually take `forced_sample_count`, which can
  differ by one (R.1 C-29). Do you want the name to say "nominal" or "estimated", or
  something tied to its use (the recorded window is twice it)?
* **Q-N5. Two kernel locals hold the forced sample count.** `n_samples` (from the offsets)
  and `forced_samples` (`tot_ind` after the forced loop) are equal. One name for both
  needs a structural change (dropping one); two names for one quantity misleads. Proposed:
  `forced_sample_count` for the first; the second removed in plan group 4 (it is then the
  same variable). Or keep both until then with `forced_sample_count` and
  `forced_samples_integrated`?
* **Q-N6. Which drawn corners are elbows A and B?** Ruling 26: elbow A is the inlet side of
  the run. In `LoopLayout` the run runs from `run_start` (x = 0, the foot of leg 1, inlet
  side) to `run_end` (x = run_length, the foot of leg 2). I take elbow A as the
  `run_start` corner and elbow B as the `run_end` corner, which also matches the junction
  force taps at node `pivot` and `N - pivot` (`moc.step`). Confirm, and the `LoopLayout`
  docstring says so (plan 1.16).
* **Q-N7. `history_type` against `kind`.** `History.kind`, the `kind` parameter of
  `canonical` and the `history_type` column are one concept (S-32). Proposed:
  `history_type` everywhere (the column already uses it). Or `kind`?
* **Q-N8. Celerity.** Kept as `celerity` (the water-hammer term an engineer reads without
  a gloss), not `wave_speed`. Agree?
