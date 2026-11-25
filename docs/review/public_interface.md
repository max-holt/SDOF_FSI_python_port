# Public interface — proposal (session R.9)

**Approved by the owner (session R.9, 25 Nov 2026), option A, with the answers of charter
rulings 76-84:** the sample rate is the second positional argument and `Integration` holds
`substep_count` and `trace_every` (Q-PI-1; the JC entry has 7 parameters, a `docs/style.md`
§11 exception); `output_type` removed (Q-PI-2); names kept (Q-PI-3); the duration terms keep
`_s` (Q-PI-4, a style exception); `daf_lumped` / `daf_jc` kept, the other pair
`force_per_length_diameter_squared_*` (Q-PI-5); S-31 and S-47 out of the bump (Q-PI-6); no
wrappers (Q-PI-7); step 4 split (ruling 83). Where the text below differs, these answers win.

Plan group 6, with 3.7 and 3.10 (rulings 47, 71). Written for the owner before anything
changes (ruling 73). Nothing here is applied yet. Section 1 is the solver entry points (step 1
of the brief), section 2 the other user-facing entry points (plan 6.3, 6.4), section 3 the
schema bump with the full old-to-new key table (step 2), section 4 the commit order, section 5
the questions.

What is fixed by earlier rulings and not reopened here: names come from
`docs/nomenclature.md` (approved, rulings 29-38); units stay "SI unless suffixed" (28); no
abstraction layer without two real users (2), parameter objects are not a layer; flags are
validated at the entry as a recorded deviation (5, plan 6.1); keyword-only arguments count
towards the limit of 6, and an entry point still above it gets a recorded exception (17).

## 1. The solver entry points

### 1.1 Today

```python
peak_response(force_history, step_qty, sample_freq, physical_length, flexural_rigidity_ei,
              celerity, mass_per_unit_len, damping_percent, dynamic_fric, nat_freq,
              restrain_freq_ratio=1, gap=0, output_type=0, trace_every=0) -> PeakResponse
peak_response_jc(force_history, step_qty, sample_freq, physical_length, flexural_rigidity_ei,
                 celerity, mass_per_unit_len, fluid_densty, fluid_area, damping_percent,
                 dynamic_fric, nat_freq, restrain_freq_ratio=1, gap=0, output_type=0,
                 trace_every=0, *, vav_denominator="fixed", parity="running",
                 fraction_profile="fixed") -> PeakResponse
```

14 and 19 parameters, positional, VBA spellings; `output_type` (0-3) decides what
`PeakResponse.history` holds; the three flags are strings validated in three places (C-12).

### 1.2 Recommended: grouped inputs, keyword-only (option A)

Four frozen dataclasses in `response`, each named for what it describes, fields from the
nomenclature, every field in SI (the `damping_percent` exception is the nomenclature's):

```python
@dataclass(frozen=True)
class PipeSpan:  # the span between the elbows and the pipe it is made of
    span_length: float  # m, between the elbows (L)
    flexural_rigidity: float  # N·m² (EI)
    mass_per_length: float  # kg/m, pipe and contents (m')
    celerity: float  # m/s, pressure-wave speed; also the force's elbow-to-elbow speed


@dataclass(frozen=True)
class Restraint:  # how the span is held: the SDOF proxy's dynamics and supports
    natural_frequency: float  # Hz, gaps open (JC: modelled with the fluid included)
    damping_percent: float  # % of critical
    friction_coefficient: float  # Coulomb μ, dimensionless
    support_gap: float = 0  # m, at the centre of mass (int 0 as today: the literal type is kept)
    closed_gap_frequency_ratio: float = 1  # f closed / f open (int 1 as today)


@dataclass(frozen=True)
class Fluid:  # the contained fluid (junction coupling only)
    fluid_density: float  # kg/m³
    flow_area: float  # m², internal cross-section (the pressure area)


@dataclass(frozen=True)
class Integration:  # how the history is integrated, and what is recorded
    substep_count: int  # substeps per sample (dt = 1 / (sample_rate * substep_count))
    trace_every: int = 0  # substeps between trace frames; 0 = no trace
```

and one settings object for the junction-coupling model choices (section 1.4):

```python
@dataclass(frozen=True)
class CouplingModel:
    mean_velocity_divisor: str = "fixed"  # "fixed" (2N + 1, F-1) | "legacy" (2N - 1, D-17)
    parity: str = "running"  # "running" (F-2) | "per_phase" (D-19)
    fraction_profile: str = "fixed"  # "fixed" (F-4b) | "legacy" (D-4)
    # __post_init__ raises ValueError on any other value (plan 6.1, recorded deviation)


VBA_COUPLING = CouplingModel("legacy", "per_phase", "legacy")  # the Excel acceptance runs
```

The entry points:

```python
peak_response(force_history, sample_rate, *, span: PipeSpan, restraint: Restraint,
              integration: Integration) -> PeakResponse                       # 5 parameters
peak_response_jc(force_history, sample_rate, *, span: PipeSpan, restraint: Restraint,
                 fluid: Fluid, integration: Integration,
                 coupling: CouplingModel = CouplingModel()) -> PeakResponse   # 7 (§11)
```

Both meet the limit of 6, so neither needs a recorded exception. Why these groups:

* **The sample rate sits with the substep count**, not beside the history. The two together
  fix `dt`; nothing else in the solver reads the sample rate on its own except the transit
  delay. This keeps the JC entry at 6. If the owner prefers the sample rate beside the
  history (`peak_response(force_history, sample_rate, *, ...)`, the style guide's "first
  two" positional), the JC entry has 7 and needs the §11 exception (Q-PI-1).
* **Celerity sits with the span.** The lumped solver needs it (the transit delay between the
  elbows) and has no fluid; it is a property of this pipe with this contents. `Fluid` then
  holds only what the junction coupling adds.
* **`Restraint` holds the frequency and the damping**, because together with the gap and the
  friction they are what the supports make of the span (the proxy's dynamics); the span holds
  only geometry and section. Plan 3.7 already names "span, restraint and fluid objects".
* **`trace_every` in `Integration`:** it is a run setting with a default, read by the same
  code that reads the substep count.
* **Frozen dataclasses, not NamedTuples:** they are user-facing, take defaults by name,
  validate in `__post_init__` (only `CouplingModel` does), and are never passed to compiled
  code (the set-up unpacks them). The internal `RunSettings` NamedTuple keeps its role and is
  renamed `KernelSettings` so the two cannot be confused.
* **Coercion stays where it is.** Today the entry converts `step_qty`, `sample_freq`,
  `physical_length`, `flexural_rigidity_ei`, `celerity`, `mass_per_unit_len` (and JC
  `fluid_densty`, `fluid_area`) with `int` / `float` and passes the rest as given; the new
  entry does exactly the same conversions on the same fields, in the same order, so every
  value reaching the kernel, and every value the trace records, keeps its type and bits.

Set-up functions (plan 3.7, C-17) take the same objects, which gives them two real users:

```python
structure.lumped_params(span, restraint, portal_frame_height, substep_duration) -> SdofParams
structure.jc_params(span, restraint, fluid, portal_frame_height, substep_duration) -> SdofParams
response.solver_setup(span, restraint, integration) -> SolverSetup   # used by tools too
```

with the shared 8-line return block extracted (`float(restrain_freq_ratio) ** 2` verbatim;
the two mass expressions not merged). Plan 3.10 (C-11): the sample grid
(`transit_delay_samples`, `nominal_forced_sample_count`) and the trace request are each one
helper both entry points call; the short-pipe fallback calls
`peak_response(force_history, span=span, restraint=restraint, integration=integration)`.

**Cost to the callers.** About 100 call sites in `tests/` (`test_differential`, `test_trace`,
`test_smoke`, `test_quirks`, `test_properties` the most) and 20 in `tools/` pass a `**kw` dict of
today's keywords, built in four places: `tools/fixture_cases.case_params` (from the frozen
fixtures, whose keys stay VBA-shaped), `tools/cases.py`, `tools/sweep_rows.solver_kwargs`, and
the case tables of `tests/test_differential.py`, `test_properties.py` and
`test_review_snapshot.py`. The differential tests must keep calling `legacy_port` with its
own keywords from the same dict. So one translator in `tools/fixture_cases.py`:

```python
solver_inputs(kw: dict) -> dict   # today's keyword dict -> {"span": ..., "restraint": ...,
                                  #   "integration": ..., ["fluid": ..., "coupling": ...]}
```

and every `**kw` call site becomes `**fc.solver_inputs(kw)` (a mechanical edit; the
assertions do not change). `tools/sweep_rows.solver_kwargs` and `tools/cases.py` build the
objects directly. The snapshot test changes in `run_solver` only (it calls the translator,
and maps the history field, below). `tools/bench.py`, `profile_delta.py` and
`review_ab.py` change their calls the same way; `review_ab.py` must run against the commit
before as well, so its cases pick the call form by what the worktree's `response` offers
(one `hasattr` in `_cases`, removed after the session).

### 1.3 `output_type`

Recommended: **remove it; always record the three histories.** `PeakResponse` gets
`displacement_history` (m), `velocity_history` (m/s) and `acceleration_history` (m/s²), each
the end-of-sample value for `2 * nominal_forced_sample_count` samples as `history` is today,
and loses `history` and `output_type`. The kernel's `_record_sample` writes the three values
it already has where it writes one today: no arithmetic changes, the stored values are the
same bits whichever `output_type` the old call used. Cost: three float arrays of
`2 * nominal_forced_sample_count` per call (about 0.4 MB for the longest golden case, 25135
samples), three stores per sample instead of one (per sample, not per substep); A/B timed
(ruling 72). Callers: about 20 test sites and the snapshot adapter read `history` with a
given `output_type`; they read the matching field instead (the adapter maps `output_type` 1/2/3 of
a stored case to the field, 0 to None, so the stored documents do not change).

Alternatives, not recommended:

* (b) `history: str | None = None` (`"displacement"` / `"velocity"` / `"acceleration"`):
  still a code that selects what is returned (style §3).
* (c) three booleans `record_displacement` etc.: three flags for one choice, and the
  same three return fields are needed anyway.

### 1.4 The junction-coupling flags

Recommended: **`CouplingModel`, a settings object with the three flags as strings**, validated
on construction (that is "at the entry": an object exists before the solver is called, so an
unknown value raises on every path, the short pipe and `rho_c == 0` included — plan 6.1, a
`DEVIATIONS.md` row and a pinning test). `vav_denominator` is renamed `mean_velocity_divisor`
(the quantity's nomenclature name); `parity` and `fraction_profile` stay. The values stay
`"fixed"` / `"legacy"`, `"running"` / `"per_phase"`, so the fixture flag sets
(`LEGACY_FLAGS`, `FIXED_FLAGS`) and the committed files keep their values, and the tests
that assert the defaults and the rejection of an unknown value keep asserting the same thing
through the new call (`CouplingModel().fraction_profile == "fixed"`; `CouplingModel(
fraction_profile="corrected")` raises). `fixture_cases.LEGACY_FLAGS` becomes the
`VBA_COUPLING` instance (and a dict form for `legacy_port`, which has no flags).

Alternative, not recommended: three booleans (`legacy_mean_velocity_divisor`, ...). Plain
flags are the style for an on/off choice, but every test of a flag's default or of an
unknown value would assert something else (ruling 6 forbids it), and the files would
change values, not only keys.

### 1.5 Option B: flat keyword-only arguments

The same parameters, renamed to the nomenclature and keyword-only after the history:

```python
peak_response(force_history, *, substep_count, sample_rate, span_length, flexural_rigidity,
              celerity, mass_per_length, damping_percent, friction_coefficient,
              natural_frequency, closed_gap_frequency_ratio=1.0, support_gap=0.0,
              trace_every=0)                                    # 13 parameters
peak_response_jc(..., fluid_density, flow_area, ..., coupling=CouplingModel())  # 16
```

Cheapest for the callers (the `**kw` dicts are renamed through the same translator), but both
entry points need a §11 exception (13 and 16 against 6), `lumped_params` / `jc_params` keep 9
and 11 loose scalars (C-17 stays open), and the trace's `inputs` echo stays a flat bag of 19
keys. Not recommended.

### 1.6 Option C: one case object

`peak_response(case: LumpedCase)`, `peak_response_jc(case: CoupledCase)`, each a dataclass of
every input. One parameter, but two near-identical 14- and 19-field records, and the set-up
functions still need the span / restraint split inside. Not recommended.

### 1.7 What stays

* The function names `peak_response` and `peak_response_jc` (and `PeakResponse`): they are
  the documented entry points, the trace's `solver` value and the tool names; "jc" is the
  solver's name throughout the documents and the sweep columns (Q-PI-3).
* `PeakResponse.summary()`, the five maxima's names and order except
  `max_applied_force` → `max_unbalance_force` (nomenclature; the frozen fixtures keep their
  column name) and `free_decay_samples` → `free_decay_sample_count`.
* The trace `inputs` echo: the new entry records its arguments grouped as they were passed,
  `{"force_history", "sample_rate", "span": {...}, "restraint": {...}, "integration": {...}}` plus `"fluid"`
  and `"coupling"` for JC, with the same values and types as today (section 3.2).

## 2. The other user-facing entry points (plan 6.3, 6.4)

### 2.1 `PeakResponse` and `Trace` (6.3; ruling 7)

`Trace` gets a column sub-record, `Trace.column: ColumnTrace | None` (None for a lumped run),
which takes the nine fields that are zero or None for a lumped run today (S-08):

```python
@dataclass(frozen=True)
class ColumnTrace:
    column_cell_count: int  # N (was pipe_seg_qty)
    end_to_elbow_cell_count: int  # (was pivot_seg_qty)
    inactive_end_cell_count: int  # (was ext_qty)
    grid_point_position: np.ndarray  # m, (2N + 1,)   (was cell_position)
    grid_point_kind: np.ndarray  # 0 A node, 1 B cell (was cell_kind)
    grid_point_moving_fraction: np.ndarray  # (was moving_fraction)
    grid_point_pressure: np.ndarray  # Pa, (frames, 2N + 1)   (was p_cells)
    grid_point_velocity: np.ndarray  # m/s, (frames, 2N + 1)  (was v_cells)
    # grid_point_count is a property: 2N + 1 (was Trace.n_cells)
```

The `Trace` fields keep their order and take the nomenclature names: `solver`, `trace_every`
(unchanged), `dt` → `substep_duration`, `step_qty` → `substep_count`, `out_max` →
`nominal_forced_sample_count`, `portal_frame_height` (unchanged), `params` → `sdof_params`,
`inputs` (unchanged), `t` → `time`, `sub_step` → `substep_index`, `sample` → `sample_index`,
`phase` → `load_phase`, `x` / `v` / `a` → `displacement` / `velocity` / `acceleration`,
`f_a` / `f_b` → `elbow_a_force` / `elbow_b_force`, `f_unbalance` → `unbalance_force`,
`f_friction` → `friction_force`, `stick` → `is_sticking`, `d_f` → `junction_force`, then
`column`. `n_frames` (a property today) becomes `frame_count`. The snapshot adapter's field
tables absorb every rename (rule 5).

`LoopLayout` (`viz/geometry`, returned to users) takes the section-6 names of the
nomenclature: `cell_position` / `cell_kind` / `moving_fraction` → `grid_point_position` /
`grid_point_kind` / `grid_point_moving_fraction`, `pivot_seg_qty` / `pipe_seg_qty` /
`ext_qty` → as `ColumnTrace`, `portal_height` → `portal_frame_height`, `spacing` →
`grid_point_spacing`, `inlet_end` / `run_start` / `run_end` / `outlet_start` →
`inlet_elbow_index` / `run_start_index` / `run_end_index` / `outlet_elbow_index`,
`elbow_pairs` → `elbow_grid_point_pairs`, `x_nominal` / `y_nominal` → `x_at_rest` /
`y_at_rest`, `leg_height` / `leg_height_2` → `inlet_leg_height` / `outlet_leg_height`;
`cell_length`, `run_length` unchanged.

### 2.2 `histories` (6.4; rulings 4, 18)

`canonical`, `from_params`, `peak_pressure_target` (today `p_cap`) and the three generators
the tools call are user-facing. Recommended: **rename to the nomenclature, keep them flat,
and record the exceptions**, because their parameters are the sweep's fifteen generator
columns one-for-one (`PARAM_KEYS`, `from_params` takes a row): grouping them would split one
flat column set into objects that the sweep must take apart again.

```python
canonical(history_type, design_pressure, amplitude_fraction, *, oscillation_frequency=None,
          noise_seed=None, envelope_reference_frequency=None, noise_cutoff_frequency=None,
          requested_noise_rms=1.0, envelope_decay_cycles=..., envelope_decay_fraction=...,
          sample_rate=..., lead_in_s=..., transit_s=0.0, tail_s=...)        # 15: §11 exception
peak_pressure_target(design_pressure, amplitude_fraction=1.0)               # was p_cap
from_params(params)                                                          # keys = PARAM_KEYS
```

`step_sine` (11) and `step_noise` (13) likewise keep their (already nomenclature) names and get
the exception. `History` fields follow the column names of section 3.3 (`kind` →
`history_type`, `sample_freq` → `sample_rate`, `p_step` → `step_pressure`, `peak` →
`pressure_max`, `n_samples` → `sample_count`, ...), so that `PARAM_KEYS`, the `History` fields
and the CSV columns are one vocabulary (S-32). The stored history documents of
`tests/review_support/` do not change (rule 6): the adapter of `test_review_support.py` maps
the new field names to the stored labels (ruling 69).

### 2.3 `export.to_*_dict` (6.4)

`to_trace_dict(result, case_id, *, git_sha=True, created_utc=None)`: the two keywords take
the names of the keys they fill (`sha` → `git_sha`, `created` → `created_utc`).
`to_sweep_dict` has 10 parameters; recommended: its provenance as one object,

```python
@dataclass(frozen=True)
class SweepProvenance:
    source: str
    tier: str | None = None
    cpu: str | None = None
    histories_version: str | None = None
    git_sha: str | None | bool = True
    created_utc: str | None = None

to_sweep_dict(rows, *, provenance: SweepProvenance, regen=None, reference=None)   # 4
```

S-33 (the default `tools/` command line held in the package): the default goes, the tool
passes its template (the six tests that rely on the default pass it too, through the tool's
constant).

## 3. The schema bump (plan 6.5)

### 3.1 What reads `inputs`

`trace.meta.inputs` and `reference entry.inputs` are free-form (`docs/data_format.md`,
"Common rules"). **The viewer reads nothing from either** (`docs/viewer/viewer.src.html`:
no `inputs` access; it reads `meta`, `params`, `outputs`, `geometry`, `frames`, `cells` and
the sweep columns, `regen`, `reference.*.case_id` / `output_names` / `excel_values` /
`rtol` / `solver`). `tests/test_export.py` reads `meta.inputs.force_history` (an array
block), `meta.inputs.vav_denominator`, `meta.inputs.fraction_profile`, their absence for a
lumped run, and in the reference entries `inputs.physical_length` and `inputs.fluid_area`
(and the pressure case's `inputs.valve_pattern`, a fixture key, unchanged). With section 1
these paths become `meta.inputs.coupling.mean_velocity_divisor`,
`meta.inputs.coupling.fraction_profile`, `inputs.span.span_length`, `inputs.fluid.flow_area`:
the same assertions on the same values.

### 3.2 Versions and refusal

`trace` schema 1 → **2**; `sweep` schema 2 → **3**. The viewer accepts only the new versions
and refuses the old with the message it already gives for sweep schema 1 (kind, the version
found, the versions it reads), plus one line: "re-export the file with `tools/export.py` from
a checkout at or after the schema bump". `docs/data_format.md` records both bumps and keeps a
one-line note of what each old schema was.

### 3.3 Old-to-new key table

Every key not listed is unchanged (`kind`, `schema_version`, `meta`, `case_id`, `solver`,
`inputs`, `params`, `outputs`, `git_sha`, `created_utc`, `geometry`, `segments`, `frames`,
`shape`, `data`, `mass`, `stiffness`, `damping`, `trace_every`, `max_static_equivalent_force`,
`max_displacement`, `max_velocity`, `max_acceleration`, `run_length`, `cell_length`, `tier`,
`subset`, `size_in`, `history_type`, `amplitude_fraction`, `histories_version`, `cpu`,
`error`, `source`, `n_rows`, the `regen` and `reference` blocks and the reference-entry
keys). The suffix rule is ruling 28: an SI quantity has no unit suffix, a non-SI one keeps
it (`_mm`, `_bar`, `_in`); the old keys that carried an SI suffix (`_m`, `_m2`, `_kg`, `_hz`,
`_s`) lose it, except the history's duration terms (Q-PI-4).

**trace.meta**

| old | new |
|---|---|
| `n_frames` | `frame_count` |
| `n_cells` | `grid_point_count` |
| `solver` values `"peak_response"` / `"peak_response_jc"` | unchanged (Q-PI-3) |

**trace.meta.params**

| old | new |
|---|---|
| `fric_acc` | `friction_velocity_step` |
| `gap` | `support_gap` |
| `ratio2` | `closed_gap_stiffness_ratio` |
| `dt` | `substep_duration` |
| `step_qty` | `substep_count` |
| `out_max` | `nominal_forced_sample_count` |
| `capped` | `is_capped` |

**trace.meta.outputs**

| old | new |
|---|---|
| `max_applied_force` | `max_unbalance_force` |
| `free_decay_samples` | `free_decay_sample_count` |

**trace.meta.inputs** (free-form; grouped as the new call, section 1.7)

| old | new |
|---|---|
| `force_history` | `force_history` |
| `sample_freq` | `sample_rate` |
| `step_qty`, `trace_every` | `integration.substep_count`, `integration.trace_every` |
| `physical_length`, `flexural_rigidity_ei`, `mass_per_unit_len`, `celerity` | `span.span_length`, `span.flexural_rigidity`, `span.mass_per_length`, `span.celerity` |
| `nat_freq`, `damping_percent`, `dynamic_fric`, `gap`, `restrain_freq_ratio` | `restraint.natural_frequency`, `restraint.damping_percent`, `restraint.friction_coefficient`, `restraint.support_gap`, `restraint.closed_gap_frequency_ratio` |
| `fluid_densty`, `fluid_area` | `fluid.fluid_density`, `fluid.flow_area` |
| `vav_denominator`, `parity`, `fraction_profile` | `coupling.mean_velocity_divisor`, `coupling.parity`, `coupling.fraction_profile` |
| `output_type` | removed (section 1.3) |

**trace.geometry** and **trace.geometry.segments**

| old | new |
|---|---|
| `cell_position_m` | `grid_point_position` |
| `cell_kind` | `grid_point_kind` |
| `moving_fraction` | `grid_point_moving_fraction` |
| `ext_qty` | `inactive_end_cell_count` |
| `pivot_seg_qty` | `end_to_elbow_cell_count` |
| `pipe_seg_qty` | `column_cell_count` |
| `x_nominal_m`, `y_nominal_m` | `x_at_rest`, `y_at_rest` |
| `run_length_m` | `run_length` |
| `leg_height_m`, `leg_height_2_m` | `inlet_leg_height`, `outlet_leg_height` |
| `portal_height_m` | `portal_frame_height` |
| `spacing_m` | `grid_point_spacing` |
| `cell_length_m` | `cell_length` |
| `inlet_end`, `run_start`, `run_end`, `outlet_start` | `inlet_elbow_index`, `run_start_index`, `run_end_index`, `outlet_elbow_index` |

**trace.frames**

| old | new |
|---|---|
| `t` | `time` |
| `sub_step` | `substep_index` |
| `sample` | `sample_index` |
| `phase` | `load_phase` |
| `x`, `v`, `a` | `displacement`, `velocity`, `acceleration` |
| `f_a`, `f_b` | `elbow_a_force`, `elbow_b_force` |
| `f_unbalance` | `unbalance_force` |
| `f_friction` | `friction_force` |
| `stick` | `is_sticking` |
| `d_f` | `junction_force` |

**trace.cells** (the block)

| old | new |
|---|---|
| `cells` | `grid_points` (S-38: "cell" is a B cell) |
| `cells.p`, `cells.v` | `grid_points.pressure`, `grid_points.velocity` (S-42: `frames.v` and `cells.v` were two velocities) |

**sweep columns** (the CSV header and `sweep.columns`; 72 columns, the same order)

| old | new |
|---|---|
| `od_mm`, `thk_mm` | `outside_diameter_mm`, `wall_thickness_mm` |
| `length_m` | `span_length` |
| `nat_freq_hz` | `natural_frequency` |
| `f_osc_hz` | `oscillation_frequency` |
| `seed` | `noise_seed` |
| `mu` | `friction_coefficient` |
| `p_design_bar` | `design_pressure_bar` |
| `p_cap_bar` | `peak_pressure_target_bar` |
| `p_peak_bar`, `p_mean_bar`, `p_rms_bar` | `pressure_max_bar`, `pressure_mean_bar`, `pressure_rms_bar` |
| `noise_rms_bar` | `scaled_noise_rms_bar` |
| `sample_freq` | `sample_rate` |
| `lead_in_s`, `transit_s`, `tail_s`, `decay_s`, `duration_s` | unchanged (Q-PI-4) |
| `n_samples` | `sample_count` |
| `p_step` | `step_pressure` |
| `p_osc` | `oscillation_amplitude` |
| `p_noise_rms` | `requested_noise_rms` |
| `f_cut_hz` | `noise_cutoff_frequency` |
| `f_ref_hz` | `envelope_reference_frequency` |
| `decay_cycles`, `decay_fraction` | `envelope_decay_cycles`, `envelope_decay_fraction` |
| `p_cap` | `peak_pressure_target` |
| `fluid_area_m2` | `flow_area` |
| `mass_per_unit_len` | `mass_per_length` |
| `ei` | `flexural_rigidity` |
| `rho_c` | `characteristic_impedance` |
| `portal_height_m` | `portal_frame_height` |
| `mass_total_kg` | `total_mass` |
| `pipe_seg_qty`, `pivot_seg_qty` | `column_cell_count`, `end_to_elbow_cell_count` |
| `jc_short_pipe` | `is_short_pipe` |
| `history_peak`, `history_mean`, `history_rms` | `force_history_max`, `force_history_mean`, `force_history_rms` (S-41: they are forces) |
| `f_eq_lumped`, `f_eq_jc` | `max_static_equivalent_force_lumped`, `_jc` (S-41: one stem with the trace's `outputs`) |
| `ratio_f_eq` | `max_static_equivalent_force_ratio` |
| `v_peak_lumped`, `v_peak_jc` | `max_velocity_lumped`, `_jc` |
| `ratio_v_peak` | `max_velocity_ratio` |
| `momentum_lumped`, `momentum_jc` | `max_momentum_lumped`, `_jc` |
| `ke_peak_lumped`, `ke_peak_jc` | `max_kinetic_energy_lumped`, `_jc` |
| `x_peak_lumped`, `x_peak_jc` | `max_displacement_lumped`, `_jc` |
| `a_peak_lumped`, `a_peak_jc` | `max_acceleration_lumped`, `_jc` |
| `f_peak_lumped`, `f_peak_jc` | `max_unbalance_force_lumped`, `_jc` |
| `f_eq_over_LD2_lumped`, `_jc` | `force_per_length_diameter_squared_lumped`, `_jc` (ruling 80) |
| `daf_lumped`, `daf_jc` | unchanged (ruling 80: DAF an accepted abbreviation) |
| `t_lumped_s`, `t_jc_s` | `wall_time_lumped`, `wall_time_jc` |

The `regen.template` placeholders follow the columns. In the reference entries,
`output_names` takes the new `PeakResponse` names (`max_unbalance_force`) and `inputs` the
grouped form above; the viewer's map from output name to column stem follows.

**Not in this bump** (values, not names; Q-PI-6): S-31 (`git_sha` a full sha in the trace and
a short tag with `-dirty` / `nogit` in the CSV; `source` a string in one place and an object
in another), and the reference entries' `solver` values `"pressure"` / `"lumped"` / `"jc"`
against the trace's function names (S-47).

### 3.4 What the bump touches

`trace.py` / `export.py` (the frame-column table of 5.3 and the sweep-column table of 5.4, so
the key change is an edit of two tables and the geometry / params blocks);
`docs/data_format.md`; the viewer source (keys only: the frame-column list, the geometry and
params reads, the sweep column names it filters and plots on, the output-name map, the two
schema versions) and the rebuilt `docs/viewer/viewer.html`; `tests/test_viewer.py`
(`FILTER_COLS`, `Y1_STEMS` and the column names it reads: the same assertions); the
committed data files re-exported (`docs/viz/data/*.json`, `*.json.gz`); the committed sweep
CSVs (`docs/sweep/*.csv`) with their header line renamed by a one-off script, every data row
byte-identical (ruling 12); `tests/review_support/` rewritten with `--write`, the stored CSV
differing in its header line only and the history documents untouched (rule 6). The viewer's
browser tests run before the commit (ruling 74).

## 4. Commit order

1. 6.1: `CouplingModel` and the entry validation (a `DEVIATIONS.md` row; a test that an
   unknown flag raises on the short pipe and at `rho_c == 0`).
2. The input types (`PipeSpan`, `Restraint`, `Fluid`, `Integration`), unused.
3. 3.7: `lumped_params` / `jc_params` / `solver_setup` take them; the shared return block.
4. 3.10 and 6.2: the new entry points (sample grid and trace-request helpers, the keyword
   fallback, `output_type` removed and the three histories recorded); the old signatures
   removed; callers in `tools/` and `tests/` moved over in the same commit (they cannot run
   against both), through `fixture_cases.solver_inputs`. A/B timed.
5. 6.3: `PeakResponse` and `Trace` renames and `ColumnTrace`; `LoopLayout` renames.
6. 6.4: `histories` and `export.to_*_dict` signatures; `History` fields.
7. 6.5: the schema bump (one commit).
8. 6.6: docstrings (docstring-only commits, one module per commit).
9. 6.7: annotations; 6.8: lint limits.

Steps 4 and 5 can be split if the owner wants the old signatures kept as thin wrappers for a
while (the brief offers it); recommended is to remove them, since every caller is in this
repository (section 6 lists what a caller outside it changes).

## 5. Questions for the owner

* **Q-PI-1.** The sample rate in `Integration` (JC entry at 6) or beside the history as the
  second positional argument (JC entry at 7, a §11 exception)? Recommended: in `Integration`.
* **Q-PI-2.** `output_type` removed and the three histories always recorded (1.3)?
  Recommended: yes.
* **Q-PI-3.** The entry-point names `peak_response` / `peak_response_jc` and the trace's
  `solver` values kept? Recommended: kept.
* **Q-PI-4.** The five history duration terms keep their `_s` suffix (the nomenclature kept
  them unchanged), although ruling 28 drops SI suffixes elsewhere in this bump? Recommended:
  keep them, they are the generator's own parameters and documented as such.
* **Q-PI-5.** Ruling 38's two columns: `dynamic_amplification_factor_*` and
  `force_per_length_diameter_squared_*`, or other names?
* **Q-PI-6.** S-31 and S-47 (value formats, not names) left out of this bump, as proposed?
* **Q-PI-7.** Old signatures removed (recommended) or kept as thin wrappers?

## 6. What a caller outside this repository changes

As applied in session R.9, plan 6.1 to 6.5 (`docs/review/plan.md`, progress R.9): the whole
interface of this proposal. Later items (6.6 docstrings, 6.7 annotations, 6.8 lint limits)
change no signature, field or key.

1. **The call.** `peak_response(force_history, step_qty, sample_freq, physical_length,
   flexural_rigidity_ei, celerity, mass_per_unit_len, damping_percent, dynamic_fric, nat_freq,
   restrain_freq_ratio, gap, output_type, trace_every)` becomes
   `peak_response(force_history, sample_freq, span=PipeSpan(physical_length,
   flexural_rigidity_ei, mass_per_unit_len, celerity), restraint=Restraint(nat_freq,
   damping_percent, dynamic_fric, gap, restrain_freq_ratio), integration=Integration(step_qty,
   trace_every))`. Everything after the sample rate is keyword-only.
2. **Junction coupling** adds `fluid=Fluid(fluid_densty, fluid_area)` and replaces the three
   keyword flags with `coupling=CouplingModel(vav_denominator, parity, fraction_profile)`
   (field `mean_velocity_divisor` for `vav_denominator`); the VBA behaviour is
   `coupling=VBA_COUPLING`. An unknown flag value now raises on every path (D-25).
3. **`output_type` is gone.** Read `displacement_history`, `velocity_history` or
   `acceleration_history` (output types 1, 2, 3) instead of `history`; `output_type` is no
   longer a field. A dict of the old keywords can be converted with
   `tools/fixture_cases.solver_inputs` (repository tool, not part of the package).
4. **Result fields.** `max_applied_force` → `max_unbalance_force`, `free_decay_samples` →
   `free_decay_sample_count` (`summary()` is unchanged). `PeakResponse` equality no longer
   compares the histories (as `histories.History`).
5. **Trace fields.** `t`, `sub_step`, `sample`, `phase`, `x`, `v`, `a`, `f_a`, `f_b`,
   `f_unbalance`, `f_friction`, `stick`, `d_f`, `dt`, `step_qty`, `out_max`, `params`,
   `n_frames` → `time`, `substep_index`, `sample_index`, `load_phase`, `displacement`,
   `velocity`, `acceleration`, `elbow_a_force`, `elbow_b_force`, `unbalance_force`,
   `friction_force`, `is_sticking`, `junction_force`, `substep_duration`, `substep_count`,
   `nominal_forced_sample_count`, `sdof_params`, `frame_count`. The column fields move to
   `Trace.column` (None for a lumped run): `n_cells`, `pivot_seg_qty`, `pipe_seg_qty`,
   `ext_qty`, `p_cells`, `v_cells`, `cell_position`, `cell_kind`, `moving_fraction` →
   `column.grid_point_count`, `.end_to_elbow_cell_count`, `.column_cell_count`,
   `.inactive_end_cell_count`, `.grid_point_pressure`, `.grid_point_velocity`,
   `.grid_point_position`, `.grid_point_kind`, `.grid_point_moving_fraction`.
   `Trace.inputs` is the call grouped as passed (`sample_rate`, `span`, `restraint`, ...).
6. **Set-up helpers.** `structure.lumped_params` / `jc_params`, `response.solver_setup` and
   `response.column_grid` take the input objects (signatures in `docs/architecture.md`).
7. **`LoopLayout`** (`viz.geometry`): `cell_position`, `cell_kind`, `moving_fraction`,
   `pivot_seg_qty`, `pipe_seg_qty`, `ext_qty`, `portal_height`, `spacing`, `inlet_end`,
   `run_start`, `run_end`, `outlet_start`, `elbow_pairs`, `x_nominal`, `y_nominal`,
   `leg_height`, `leg_height_2`, `n_cells` → `grid_point_position`, `grid_point_kind`,
   `grid_point_moving_fraction`, `end_to_elbow_cell_count`, `column_cell_count`,
   `inactive_end_cell_count`, `portal_frame_height`, `grid_point_spacing`,
   `inlet_elbow_index`, `run_start_index`, `run_end_index`, `outlet_elbow_index`,
   `elbow_grid_point_pairs`, `x_at_rest`, `y_at_rest`, `inlet_leg_height`,
   `outlet_leg_height`, `grid_point_count` (6.3c).
8. **`histories`** (6.4a): `canonical(history_type, design_pressure, amplitude_fraction, *,
   oscillation_frequency, noise_seed, envelope_reference_frequency, noise_cutoff_frequency,
   requested_noise_rms, envelope_decay_cycles, envelope_decay_fraction, sample_rate,
   lead_in_s, transit_s, tail_s)` (was `kind`, `p_design`, `f_osc`, `seed`, `f_ref`, `f_cut`,
   `p_noise_rms`, `decay_cycles`, `decay_fraction`, `sample_freq`); `p_cap` →
   `peak_pressure_target(design_pressure, amplitude_fraction)`; `History.force(flow_area)`.
   `History` fields and `PARAM_KEYS` (the `from_params` keys): `kind`, `sample_freq`,
   `p_step`, `p_osc`, `f_osc`, `p_noise_rms`, `f_cut`, `f_ref`, `seed`, `decay_cycles`,
   `decay_fraction`, `p_cap`, `n_samples`, `peak`, `p_min`, `mean`, `rms`, `noise_rms` →
   `history_type`, `sample_rate`, `step_pressure`, `oscillation_amplitude`,
   `oscillation_frequency`, `requested_noise_rms`, `noise_cutoff_frequency`,
   `envelope_reference_frequency`, `noise_seed`, `envelope_decay_cycles`,
   `envelope_decay_fraction`, `peak_pressure_target`, `sample_count`, `pressure_max`,
   `pressure_min`, `pressure_mean`, `pressure_rms`, `scaled_noise_rms`. The error messages
   are unchanged (they still name `f_osc`, `seed`, `f_ref`, `p_cap`, `kind`).
9. **`export`** (6.4b): `to_trace_dict(result, case_id, *, git_sha=True, created_utc=None)`
   (was `sha`, `created`); `to_sweep_dict(rows, *, provenance=SweepProvenance(source, tier,
   cpu, histories_version, git_sha, created_utc), regen, reference=None)`: `regen` is
   required (the default `tools/` template left the package, S-33; the tool's templates are
   `tools/sweep_document.golden_regen` / `sweep_regen`). `response.RunSettings` is
   `KernelSettings` (internal).
10. **Exported files** (6.5): trace schema 2 and sweep schema 3, every key through the table
    of §3.3; `meta.inputs` and the reference entries' `inputs` are grouped as the call
    (§1.7; the reference entries have no `coupling` group, the fixtures name no flags);
    `output_names` say `max_unbalance_force`. The viewer reads only the new versions: a file
    written before the bump is re-exported with `tools/export.py`, and a sweep CSV written
    before it needs its header line renamed (55 of the 72 names; the rows are unchanged).
