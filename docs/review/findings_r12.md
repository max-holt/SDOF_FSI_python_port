# Close-out cold read — findings (session R.12, 25 Nov 2026)

Four `clean-code-reviewer` agents read the code on `7e726e0` with the instructions of the
first review (style guide and charter only; no `NOTES.md`, git history, architecture or
earlier findings): solver core × {architecture and functions, names and documentation},
supporting Python × the same two. One `finding-verifier` per module then tried to refute all
of that module's findings together (11 verifiers, not one per finding). Overlapping findings
are merged; ids are this session's. 132 checked: **125 confirmed** (most with corrections,
folded in below), **4 refuted**, **1 split**, **2 unclear**. `docs/review/report.md` gives
the summary and the recommendations; `findings.md` stays the governing list of the review.

Recommendation: **now** = documentation that is wrong today, R0 (docstring, comment or tool
flag), fix before or right after the merge; **S6** = defer to Stage 6 (a structural or naming
change that needs the gates and an A/B); **leave** = refuted, a Nit (ruling 8), an ungated
tool (ruling 24), a schema-bump item, or an owner question. "intro" marks a finding the
refactor introduced (the code it names did not exist at `177c8b1` in that form).

## Solver core

| id | sev | verdict | finding (corrected) | rec |
|---|---|---|---|---|
| R1 | Design | confirmed, intro (R.9) | `response._trace_request` feeds `loads.elbow_forces` from the exported input echo (`inputs["force_history"]`, `inputs["sample_rate"]`, response.py:611-614) | S6 (with R3) |
| R2/T4 | Design | confirmed, intro (R.5) | `trace.build_trace` takes response's private `_KernelResult` and `KernelSettings` (TYPE_CHECKING import, trace.py:73) to read five integers; no runtime cycle | S6 |
| C1 | Design | confirmed, intro (R.6) | `coupling.py` holds only `FluidConstants` and the factory `fluid_column`; its module docstring (1-22) describes `_integrate_kernel` and `moc.step` | now (cut docstring 3-18); move into moc: S6 |
| S1 | Design | confirmed, intro (R.9) | `structure` types its set-up functions with `response.PipeSpan/Restraint/Fluid` (TYPE_CHECKING only); its docstring says it knows nothing of fluid, `jc_params` reads density and area | now (docstring, with S2); move: S6 |
| M1 | Design | confirmed, intro (R.8) | `moc.display_moving_fractions`, a display-only third profile, lives in the solver module (only caller viz/geometry.py:250) | S6 |
| L1 | Readability | confirmed | §11 reason for nesting 4 of the two loads walks is wrong: the 4th level is the phase dispatch inside each consumer, not the two walks; per-sample extraction keeps the walks apart; duplicated 13-line field unpack (423-436 = 526-539) | now (restate §11); change: S6, needs ruling 86 revisited and an A/B |
| L2 | Readability | confirmed | `loads._schedule` runs both phases in ~115 lines; elbow-B position handed over as shared locals | S6 (A/B) |
| L3 | Readability | confirmed | transit phase rewrites `_next_position` inline (315-322); its `min(history_column, …)` is a no-op | S6 |
| R3 | Readability | confirmed | the two entry points repeat ~25 lines of set-up and echo; one helper would reorder calls, needs a prefix and a suffix helper | S6 |
| R4 | Readability | confirmed | `_kernel_inputs` does three set-up jobs (~49 lines) | S6 |
| R5/T1 | Design | confirmed, intro (R.1b comment, R.11 4th copy) | the record window "2 × nominal forced samples" in four places, its "for Ben to confirm" comment three times; `export.is_capped` re-derives it | S6 |
| R6 | Readability | confirmed | kernel local `forced_samples` always equals `forced_sample_count`; ruling 33 kept it until group 4, which is done | S6 (kernel; §11 count then 54) |
| R7 | Readability | confirmed | response module docstring: parity "applied by `_integrate` … as `step_index` to the coupling"; Notes `n + off` (32-33, 1057-1061) — wrong | now |
| R8 | Readability | confirmed | `peak_response_jc` docstring names `Trace.p_cells` / `v_cells`, which do not exist (434-435) | now |
| R9 | Readability | confirmed | `_trace_request` documents `solver : {"lumped", "jc"}`; callers pass `"peak_response"` / `"peak_response_jc"` | now |
| R10 | Readability | confirmed | "forced phases" / "forced substep" mean transit + forced (288, 732, 761, 1213); prose only, the count names are ruled | S6 |
| R11–R14 | Readability | confirmed | `first_substep_number` two meanings; `_record_frame` parameter `loads` shadows the module; free-decay reference displacement under three names; `_sample_grid` returns no grid | S6 |
| R15 | Readability | confirmed / unclear | stage, session and NOTES.md labels in docstrings (response, moc, structure, coupling, loads, trace) | leave: owner (no style rule forbids provenance) |
| R16 | Readability | confirmed | comments say `out_max` (1118, 1324); moc.py:645 places the `rho_c = 0` check in the entry point (it is in `coupling.fluid_column`) | now |
| R24 | Readability | confirmed | that the column gets the previous substep's acceleration (`state.a * dt`, 1287, 1338) is said only in coupling.py's docstring | now (comment) |
| R17–R23 | Nit | confirmed | bare 0/1 parity start, positional `False`, `_record_frame` §4 departure not in §11, import order, units of `_KernelResult.x/v/a`, "Phase 3 … R", dtype of `_largest_magnitude` | leave (R19: record in §11) |
| M2 | Readability | confirmed | `FluidColumn` built positionally from 13 values in another order than `FluidConstants` | S6 |
| M3 | Readability | confirmed, intro (R.9) | `mean_velocity_divisor` names a string choice, an int and a function; the internal parameter is still `vav_denominator`; moc.py:28 names `CouplingModel.vav_denominator` (gone); value sets exist (`PARITIES`, …) but literals are re-checked | now (moc.py:28); rest S6 |
| M4–M7 | Readability | confirmed | "pivot" for the elbow and for the count; VBA names as primary definitions (`pipeSegQTY`, `extQTY`, `totInd`, `fluidDensty`); error messages in VBA names (tests match `"pivot > ext"`); A nodes "cell-centred" | S6 |
| M8–M10 | Nit | confirmed | `empty_column` placeholders, `is_short_pipe` arguments, 0.5 / 1.5 offsets | leave |
| S2, S3, S6 | Readability | confirmed | structure docstring names only `GetPeakResponse`; `f_applied` vs `applied_force` (ruling 37); stick branch unexplained | now (S2, S6); S3: S6 |
| S4, S5 | Nit | confirmed | "sub-step", `w2` | leave |
| C2 | Nit | confirmed | "Acoustic impedance" | leave |
| L4 | Design | **refuted** | phase codes in two modules: the split is documented (free decay defined with its consumer) | leave |
| L5, L6, L12 | Readability | confirmed | "sample" for a list of forces; `_Run` vs `walk`; VBA loop vocabulary in comments | S6 |
| L7–L11 | Nit | confirmed | (L7 already rejected as C-N04) | leave |

## Supporting Python

| id | sev | verdict | finding (corrected) | rec |
|---|---|---|---|---|
| T2 | Design | confirmed, intro (R.8/R.9) | the column grid in three forms (`InterleavedGrid`, `ColumnTrace`, `LoopLayout`) packed and unpacked, with different field names | S6 (snapshot adapter map edited, not regenerated) |
| T3 | Design | confirmed, intro (R.4/R.5) | `TraceRequest` carries the kernel's elbow-force generator (annotated `object`) and `build_trace`'s inputs; its docstring says all of it is for building the trace | now (docstring, annotation, unit); split: S6 |
| G1 | Design | confirmed | lumped geometry rebuilt from `Trace.inputs["span"]` and response internals; celerity held twice | S6 (a `Trace` field: public-API territory) |
| E3 | Design | confirmed | sweep CSV column types restated in `sweep_rows.history_from_row` and the ungated `sweep_report._load` | S6 (gated part) |
| W1 | Design | confirmed | `sweep_rows` re-derives the modal mass `(L + h·4/3)·m`; same operands and order as `structure.lumped_params` | S6 |
| K1 | Design | confirmed | tools re-derive the forced substep count (`cases.forced_substep_count`; `+ 1` follows loads.py:448); can differ from the solver only in edge cases | S6 (bench half ungated) |
| K2 | Design | confirmed | step cases built in the fixture vocabulary; "is this JC" decided three times | S6 |
| K3, K4, W2 | Design | confirmed | bench, golden_report, sweep_report re-derive set-up / loaders / fixed inputs | leave (ungated) |
| T5, T6, T7, T8, T9, T10 | Readability | confirmed | `check_memory` two jobs; `build_trace` two jobs; `nominal_forced_sample_count` defined as "the VBA outMax"; module docstring names a kernel counter `n` that is gone (T8, now); `stride` vs `trace_every`; retired `n_cells` / `cap` / `n_frames` | T8 now; rest S6 |
| T11, T12 | Nit | **refuted** | (tests index `TraceBuffers` by position; `FrameRow` is compiled-only) | leave |
| T13, G6 | Readability | unclear | session labels in module docstrings | leave: owner |
| G2, G4 | Readability | confirmed | `loop_layout` ~75 lines (= open SP-20); "cell" for grid point, undefined "pivot" | S6 |
| G3 | Readability | confirmed | `LoopLayout.elbow_grid_point_pairs` read only by tests, but in the approved public interface | leave: owner |
| E1, E2 | Readability | confirmed | twelve `_finite` calls; three spellings of the array NaN check | S6 |
| E4 | Readability | confirmed | data_format.md meaning column cites pre-bump keys (`cell_position_m`, `leg_height_m`, `mass_total_kg`, `ratio_*`, `out_max`, …) | now (text only, no export rewrite) |
| E5–E8, E11 | Readability | confirmed | data_format.md: keys defined only by VBA name (81, 92, 112); "cell" / "pivot"; "sub-step"; architecture.md pointers; `display_moving_fractions` | now (E11 narrow); rest S6 |
| E9, E10, E15 | Readability | confirmed | `n_rows` (kept on purpose at the R.9 bump), `force_history_max` is a magnitude, `grid_point_count` 0 for lumped | leave (next schema bump) |
| H1–H3 | Readability | confirmed | generator prologue (step / step_sine only), dispatch and defaults repeated (defaults are the clean part), RMS three times | S6 |
| H4 | Readability | confirmed | §11 reason for `histories.canonical` fits `step_sine` / `step_noise`, not `canonical` (not `PARAM_KEYS`, never called by `from_params`); same text in its `noqa` | now (restate; ruling 90 accepted the text, owner) |
| H5–H7, H10 | Readability | confirmed | retired names in constant docstrings (`p_step`), `_KIND_SPECIFIC_PARAMS`, unit-less defaults | H5 now; rest S6 |
| W3, W4, W7–W10, W12, W13 | Readability | confirmed | identity map `HISTORY_PARAM_COLUMNS`; `sweep_jc.run` five jobs; `estimated_cells`; old `Case` / `TIERS` names; `p_design`, `p`; unit-less sweep constants; VBA names in `--help` | S6 |
| W11 | Readability | confirmed | exported `regen.note` text carries session labels and names moved functions; data_format.md:205 cites `sweep_jc.COLUMNS` | leave (export rewrite); data_format line: now |
| W6 | Readability | **refuted** | (the layout string is printed and asserted by tests) | leave |
| W5, K5–K11 | Readability | confirmed | git / CPU helpers, flag set ×3, `MM_PER_M` int vs float (no bit risk), step defaults, `StepSpec` names, `tg` alias and `kw`, bench names | S6 (gated parts); ungated leave |
| K14 | Readability | confirmed, intro (R.10) | `tools/review_baseline.py` lacks `--ignore-noqa`: since the targeted `noqa` it reports 0 in exactly the columns of the §11 exceptions | now |
| W14–W20, K12, K13, E13, E14, G5, H8, H9 | Nit | confirmed (H9 split) | | leave |
