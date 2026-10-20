# Port review — Stage 1 literal port (HEAD 648d158)

Review of `src/surge_sdof/legacy_port.py` and `vba_compat.py` against
`legacy/vba/Existing Code.bas`, written at the close of Stage 1 as the input to the
Stage 2–5 refactor. Two independent passes:

* the `port-reviewer` subagent on `git diff 125e73e HEAD` (diff + VBA only, no
  implementation context): **no correctness findings**; four non-blocking observations,
  folded into §3 and §5 below;
* a line-by-line read of the port against the VBA by the session itself, plus the
  measurements quoted as evidence (all reproducible with the commands shown).

Line numbers: `VBA n` = `legacy/vba/Existing Code.bas`, `py n` = `legacy_port.py`.
`U1`, `U2` = `UBound(forceHistory, 1 / 2)`; `s` = `stepQTY`; `N` = `pipeSegQTY`;
`unb` = `unballanceStepQTY`.

---

## 1. Numerical constants and magic numbers

"Unit-dependent" means the constant only has its intended meaning when the inputs are in
the units the VBA comments assume (m, s, kg, Pa internally; bar, m³/h, mm², Cv at the
`GetPressureResponse` interface). Dimensionless constants survive a change of units.

### 1.1 Shared by `GetPeakResponse` and `GetPeakResponseJC`

| Constant | VBA | py | Role | Unit-dependent |
|---|---|---|---|---|
| `pi = 3.14159265358979` | 324, 639 | 484, 848 | 15-digit literal; `math.pi - literal = 3.1e-15` (rel 1e-15). A refactor that substitutes `math.pi` is *not* bit-preserving | no |
| `12` in `-12·EI/(2πf)²` | 384, 386, 721, 723 | 505, 511, 875, 881 | Portal-frame leg stiffness coefficient (`12EI/h³` form) fed to `solvePoly` as `varA` | no |
| `0.5 + 1.5·(h/(L+h))²` | 386, 723 | 514-515, 884-885 | Frame-stiffness correction applied in the 11 refinement passes | no |
| `4/3` (`massPerUnitLen * 4 / 3`) | 384, 386, 389-392, 721-729 | 507, 519, 522, 877, 889, 892-914 | Effective mass of the two frame legs (`varC`, and the `+ h·4/3` in mass/stiffness/damping/fricAcc) | no |
| `10` (`For i = 0 To 10`) | 385, 722 | 509, 879 | **11** refinement calls of `solvePoly` after the seed call. Measured on the 78 golden parameter sets: last-pass relative change of `portalFrameHeight` is 0 … 1.1e-12, i.e. converged well before 11; not safe to shorten without a tolerance argument | no |
| `100` in `dampingPercent / 100` | 391, 728 | 524, 907 | Percent → fraction | no (percent is a unit, but fixed by the interface) |
| `2 * (k·m)^0.5` | 391, 728 | 524, 900-905 | Critical damping; `^ 0.5` is a `pow` call, not `sqrt` (see §3.1-d) | no |
| `0.5` in `fricAcc = 0.5·dynamicFric·9.81·dt` | 392, 729 | 525, 910 | "Weight fraction": Coulomb friction acts on half the weight (one half-wave of the mode, or half the span carried by the restraint — intent not documented). `fricAcc` is a velocity increment per sub-step (m/s) | **yes** (via 9.81 and via `dynamicFric` being a coefficient against *weight*) |
| `9.81` | 392, 729 | 525, 912 | g; converts `dynamicFric` (coefficient) to acceleration | **yes** (m/s²; the VBA comment on `dynamicFric` says "assumes units are m, sec") |
| `0.000001` in `sign(v, 0.000001)` | 428, 498, 538, 577, 856, 982, 1078, 1172 | 583, 655, 699, 734, 1114, 1273, 1409, 1524 | Dead-zone of the friction sign: when `fricAcc <= |v| < 1e-6` the friction term is applied with sign 0, i.e. not at all | **yes** (m/s) |
| `0.01` in `Do While x · xZero > 0.01` | 569, 593, 1109, 1188 | 720, 746, 1430, 1536 | Free-decay (phase 3) runs only while `x·xZero > 0.01`; with `xZero = x` at entry this is `x² > 0.01`, i.e. `|x| > 0.1`. In metres it is never reached for pipework (golden max `xMax² = 2.4e-5`, see §4) | **yes** (length²) |
| `k / (stepQTY − 1)` | 422, 491-492, 531-532, 850, 975-976, 1071-1072 | 567-569, 636-641, 680-685, 1097-1099, 1253-1258, 1387-1394 | Linear ramp between consecutive samples over `s−1` sub-steps; `s = 1` divides by zero (D-7). Note the ramp reaches the next sample at `k = s−1` and the next sample's `k = 0` repeats it (§3.2-b) | no |
| `(totInd − 1)·s + 1 + k > unb·s` | 446, 874 | 596, 1127 | Phase-1 exit: integrate `ceil(unb·s)` sub-steps before the delayed wave arrives | no |
| `outMax · 2` | 378, 598, 715, 1193 | 498, 749, 868, 1539 | Result-history length: twice the sample count incl. delay (room for phase 3) | no |
| `0 To 4` result layout | 611-616, 1206-1211 | 758-769, 1548-1559 | `[static-equivalent force, xMax, vMax, aMax, FMax]` | no |

### 1.2 `GetPeakResponseJC` only

| Constant | VBA | py | Role | Unit-dependent |
|---|---|---|---|---|
| `Const useUndamped = False` | 640 | 849 | Selects the AFT "infinite pipe" boundary (dead branch) instead of the decaying boundary | no |
| `Const dampingA = 0.25` | 641, 834, 846 (and ×4 copies) | 850, 1070, 1091, … | First-order low-pass on the junction force: `dF = 0.25·dF_old + 0.75·(new)`. A per-sub-step filter: its time constant is `dt / ln(4)`, so its physical effect **changes with `stepQTY` and `sampleFreq`** | no in units, but **step-size dependent** |
| `Const extQTY = 4` | 642, 107, 123 | 851, 188, 208 | Grid cells at each end that receive no mass acceleration (`interpFraction* = 0`); also the base of `pivotSegQTY` | no (cells) |
| `3` in `interpFractionB`: `If n < 3` | 124 | 209 | Node-centred variant uses 3 where A uses `extQTY` (D-4) | no |
| `0.5` in `interpFractionA`: `(n − 0.5 − extQTY)` | 111, 115 | 192, 196 | Cell-centre offset of the ramp | no |
| `2 ^ ((celerity·dt)/physicalLength)` | 731 | 918 | `dacayFactor`: end-cell pressure decays by 2^(c·dt/L) per even update (a half-life of one pipe transit); replaces the undamped boundary | no (ratio) |
| `2` in `pivotSegQTY = 4 + CLng(h/(2·c·dt))` | 733 | 920 | Cell length is `2·c·dt` (two sub-steps per cell, one per half-update) | no |
| `2 + CLng(L/(4·c·dt) + pivotSegQTY)·2` | 734 | 921 | `pipeSegQTY` even by construction; `L/(4c·dt)` = half the span in cells | no |
| `pipeSegQTY − 2·pivotSegQTY <= 2` | 736 | 923 | Short-span fallback to the lumped solver | no |
| `2·pipeSegQTY − 1` | 802 (×4) | 1015, 1172, 1306, 1441 | Divisor of `vAv`; the sum has `2N + 1` terms (§3.2-a) | no |
| `3`, `−3`, `+1` | 806-807 (×4) | 1019-1030, … | AFT infinite-pipe extrapolation weights (dead branch) | no |
| `/ 2` on the four-point `dF` | 834 (×4) | 1070-1075, … | Even-update junction force averages two cells at each pivot | no |

### 1.3 `solvePoly`

| Constant | VBA | py | Role | Unit-dependent |
|---|---|---|---|---|
| `Const relax = 0.25` | 138 | 228 | Newton under-relaxation | no |
| `(−varA/varB)^(1/3)` | 143 | 229 | Seed; negative base is error 5 in VBA, complex in Python (§3.1-a) | no |
| `For i = 1 To 100` | 144 | 230 | Iteration cap. Measured on the golden sets: 35-56 iterations per call, cap never hit (0 of 936 calls) | no |
| `0.000001` in `Abs(errorVal/varA) < 1e-6` | 146 | 232 | Relative residual tolerance | no |

### 1.4 `GetPressureResponse`

| Constant | VBA | py | Role | Unit-dependent |
|---|---|---|---|---|
| `CLng(closureTime/timeStep)` | 206 | 298 | `outMax`; each loop iteration is **two** time steps (comment at 243), so the result spans `2·closureTime` | no |
| `1 + CLng(min(outMax, L/(c·dt))/2)` | 207 | 299 | `pipeSegQTY`: pipe truncated to what a wave can traverse in `closureTime`; the pump boundary sits there | no |
| `UBound1·UBound2·timeStep/closureTime` and `·2` | 213, 244-245, 263 | 306, 343-344, 360 | `factor`: pattern samples per time step; the valve pattern is stretched evenly over `closureTime` | no |
| `1000000 / (… 60·60)` | 217, 218 | 310, 314 | m³/h and mm² → m/s | **yes** |
| `(density/1000)·100000 / (valveCv·0.865·1e6/(area·3600))²` | 218 | 311-315 | Valve loss Pa/(m/s)²: SG = ρ/1000, bar → Pa, Cv → Kv (0.865) | **yes** (every factor) |
| `pressureDropFromPump · 100000` | 220, 287 | 317, 397 | bar → Pa | **yes** |
| `1 + pipeSegQTY·2` | 220 | 317 | Loss per half-cell: `2N + 1` half-cells | no |
| `0.999999999` | 267 | 367 | "Valve fully closed" threshold on `closure`; avoids `1/(1 − closure)` blowing up | no |
| `0.9` | 278 | 386 | Friction clamp in the first MoC half-loop: `loss <= 0.9·v` | no |
| `0.9 · rhoC` | 293 | 410 | Friction clamp in the second half-loop (D-6): `0.9·ρc` is ~1e6 for water, so this clamp is effectively absent | **yes** (the two clamps have different dimensions) |
| `(min(0, vA)/velAtPump)²` | 287 | 401 | Pump ramp: pressure rises from operating to shut-in as flow at the pump falls to zero; `pumpRampPressure` in bar | **yes** (bar via the 100000) |

---

## 2. Duplicated code — refactor map for Stage 4

All line ranges are inclusive. "Identical" was verified with `diff` on the
whitespace-stripped VBA text (`sed -n 'a,bp' | sed 's/^[ \t]*//'`).

### 2.1 The three integration phases (both peak solvers)

| Phase | `GetPeakResponse` VBA | py | `GetPeakResponseJC` VBA | py |
|---|---|---|---|---|
| Input normalisation (Range / AddDimension / ArrayStartOne) | 365-373 | 490-493 | 702-710 | 860-863 |
| `unb`, `outMax`, `resultArray`, `kOverlap`, `dt` | 375-382 | 495-502 | 712-719 | 865-872 |
| Portal-frame solve (seed + 11 passes) | 384-387 | 504-520 | 721-724 | 874-890 |
| Mass / stiffness / damping / fricAcc | 389-392 | 522-525 | 726-729 | 892-916 (fluid-corrected) |
| JC grid set-up, fallback, arrays | — | — | 731-761 | 918-960 |
| State init, `forceA = forceHistory(1,1)` | 394-401 | 527-538 | 763-771 | 962-976 |
| **Phase 1** (delay: `forceA` constant, `forceB` ramps) | 403-466 | 540-610 | 775-894 | 982-1141 |
| `jB`/`iB` re-base after phase 1 | 468-471 | 616-618 | 896-899 | 1144-1146 |
| **Phase 2** (both forces ramp, `kOverlap` split) | 473-567 | 620-718 | 901-1107 | 1148-1428 |
| — k-loop A: `0 To s−kOverlap−1` | 490-516 | 635-667 | 918-1000 | 1163-1285 |
| — `iB/jB` advance + `iBmax/jBmax` | 517-529 | 668-678 | 1001-1013 | 1286-1296 |
| — k-loop B: `s−kOverlap To s−1` | 530-556 | 679-711 | 1014-1096 | 1297-1421 |
| **Phase 3** (free decay while `x·xZero > 0.01`) | 568-608 | 719-755 | 1108-1203 | 1429-1545 |
| `outputType = 0` summary | 610-617 | 757-769 | 1205-1212 | 1547-1559 |

Lumped vs JC: phases 1-3 of the JC function are the lumped phases with the MoC block
inserted at the top of every k-loop body and `dF +` prepended to `aNew`. Everything else
(index walk, exits, output switch) is textually the same.

### 2.2 The SDOF kinematics step (8 copies)

| Copy | VBA | py | Differs from phase-1 copy by |
|---|---|---|---|
| lumped phase 1 | 424-445 | 571-595 | — |
| lumped phase 2 A | 494-515 | 643-667 | identical |
| lumped phase 2 B | 534-555 | 687-711 | identical |
| lumped phase 3 | 573-591 | 723-744 | no `(forceA − forceB)` term; no `FMax` update |
| JC phase 1 | 852-873 | 1101-1126 | `dF +` in `aNew` |
| JC phase 2 A | 978-999 | 1260-1285 | identical to JC phase 1 |
| JC phase 2 B | 1074-1095 | 1396-1421 | identical to JC phase 1 |
| JC phase 3 | 1168-1186 | 1512-1534 | `dF −` restoring term only; no `FMax` update |

Candidate: one `sdof_step(F, x, v, a) -> (x, v, a)` with the max-trackers outside, and
`F = dF + forceA − forceB` (phase 1-2) or `F = dF` (phase 3). The phase-1 `Exit For`
test (446 / 874) and the phase-3 `xZero` reset (593 / 1188) stay in the callers.

### 2.3 Force interpolation (6 copies)

| Where | VBA | py |
|---|---|---|
| phase 1 (`forceB` only) | 422, 850 | 567-569, 1097-1099 |
| phase 2 A (`forceA`; `forceB` with `k + kOverlap`) | 491-492, 975-976 | 636-641, 1253-1258 |
| phase 2 B (`forceA`; `forceB` with `k − s + kOverlap`) | 531-532, 1071-1072 | 680-685, 1387-1394 |

### 2.4 Column-major index walk with wrap (`imax/jmax`, `iBmax/jBmax`)

| Where | VBA | py |
|---|---|---|
| phase 1 (`j/i` from `jB/iB`, clamp when `jB > U2`) | 407-420, 779-792 | 553-564, 994-1005 |
| phase 2 `imax/jmax` | 476-482, 904-910 | 623-628, 1151-1156 |
| phase 2 `iBmax/jBmax` (before k-loop A) | 483-489, 911-917 | 629-634, 1157-1162 |
| phase 2 advance `iB/jB` | 517-522, 1001-1006 | 668-672, 1286-1290 |
| phase 2 `iBmax/jBmax` (before k-loop B) | 523-529, 1007-1013 | 673-678, 1291-1296 |
| `GetPressureResponse` valve-pattern walk (same idea, `floor`/`modDbl` based) | 244-265 | 343-365 |

Note the phase-1 variant uses `jmax = min(j, U2)` (418) where phase 2 uses `jmax = j`
(480); they coincide because `j <= U2` always holds there. Only `U2 = 1` has ever been
tested against Excel (§4).

### 2.5 The MoC block in `GetPeakResponseJC` (4 copies, not 3)

Phase 2 has two k-loops, so the block appears four times. All four are **byte-identical**
after whitespace stripping (`diff` of VBA 795-847 against 920-972, 1016-1068, 1113-1165:
no output).

| Copy | VBA | py |
|---|---|---|
| phase 1 | 795-847 | 1007-1093 |
| phase 2 A | 920-972 | 1164-1250 |
| phase 2 B | 1016-1068 | 1298-1384 |
| phase 3 | 1113-1165 | 1433-1509 |

Inside each copy: parity test (795), `vAv` (797-802), boundary update — dead
`useUndamped` branch 803-818 / live decay branch 820-823 —, even-cell sweep 825-829,
B-velocity sweep 830-833, even `dF` 834; odd-cell sweep 837-841, A-velocity sweep
842-845, odd `dF` 846. Candidate: `moc_step(parity, a, arrays…) -> dF`, with
`interpFractionA/B` precomputed once per `n` (they depend only on `n`, `pivotSegQTY`,
`pipeSegQTY`; today they are recomputed 2·N times per sub-step, ~1e9 calls per JC case).

**Hazard for a single-loop refactor.** The parity index is `k + (totInd − 1)·s` with the
phase's own `k` range, not a running step counter:

* phase 1 exits mid-sample at `k_exit` (first `k` with `(totInd−1)·s + 1 + k > unb·s`);
  phase 2 restarts at `k = 0`, index `T·s`. For even `s` the alternation is continuous
  only when `k_exit` is odd. Golden JC cases (L = 24): `k_exit = 21`, continuous. A
  different span or `stepQTY` can double-update one half-grid at this boundary.
* phase 3 uses `k = 1 To s`; its first index `T·s + 1` has the same parity as the last
  phase-2 index `T·s − 1`, so the odd half-grid is always updated twice in a row at the
  2→3 boundary (unexercised: phase 3 never runs on the golden inputs).

A refactor must keep the index formula per phase or prove the parity sequence equal.

### 2.6 `GetPressureResponse` MoC half-loops (2 copies, not identical)

| Copy | VBA | py | Difference |
|---|---|---|---|
| A-from-B (`1 To min(N, totInd)`) | 275-285 | 382-392 | clamp `0.9`, `velInitLocal` at cell centres `i·2` |
| B-from-A (`0 To min(N−1, totInd)`) | 290-300 | 406-416 | clamp `0.9·rhoC` (D-6), `velInitLocal` at `(1 + i·2)` |

### 2.7 Stage 5 note (performance, not correctness)

`force_history[i, j]` yields `numpy.float64`, so after the first sub-step `x`, `v`, `a`,
`forceA/B` and `dF` are numpy scalars (verified: `get_peak_response(...)[1]` is
`numpy.float64`). Scalar numpy arithmetic is several times slower than Python floats and
is what `np.errstate` governs (§3.1-c). Numba removes both effects; the `**` semantics in
§3.1-d are then the thing to watch.

---

## 3. Discrepancies not already in DEVIATIONS.md

### 3.1 Port vs VBA (behaviour differs; none affect the golden inputs)

**a. `solvePoly` with a negative cube-root base returns a complex number instead of
raising.** VBA 143 `(-varA / varB) ^ (1 / 3)` raises error 5 for a negative base; py 229
`(-var_a / var_b) ** (1 / 3)` returns a complex and the Newton loop continues in complex
arithmetic. Evidence: `solve_poly(12.0, 1.0, 1.0)` → `(1.1009+1.2887j)`. Downstream the
complex `mass` reaches `result_array[...] = …` and raises `TypeError` (verified), so the
call still fails, but later and with a different exception; in the JC fallback test
(`pipeSegQTY − 2·pivotSegQTY <= 2`) a complex comparison would raise `TypeError` even
earlier. Reachable only with `EI < 0` or `L·massPerUnitLen < 0`. Mentioned in NOTES.md,
not in DEVIATIONS.md. Suggest a row "preserved as an error, different exception".

**b. VBA Integer/Long overflow is not emulated.** `stepQTY As Integer` (VBA 309, 622)
overflows above 32767 at the call; every `CLng` (`outMax`, `pipeSegQTY`, `kOverlap`,
`pivotSegQTY`, …) raises error 6 above 2³¹−1. `clng` (vba_compat 34) returns an unbounded
`int`. Documented in NOTES.md ("Judgement calls"), not in DEVIATIONS.md.

**c. Floating overflow: mixed semantics.** VBA raises error 6 on any Double overflow.
In the port, the integration state is numpy (§2.7) and runs under
`np.errstate(over="raise")`, so it raises `FloatingPointError`; the set-up arithmetic
(`solvePoly`, mass/stiffness, `dacayFactor`, `valveLoss`) is pure Python and would
produce `inf` (or `OverflowError` only from `**`). Documented in the module header and
NOTES.md, not in DEVIATIONS.md.

**d. `^` vs `**` (last-bit).** Both Python `float.__pow__` and `numpy.float64.__pow__`
call C `pow` for every exponent used here; measured on 10⁶ random doubles: `x**2`,
`x**0.5`, `x**3` equal `math.pow` in every case, whereas `x*x` differs from `pow(x, 2)`
in 872 cases, `math.sqrt(x)` from `pow(x, 0.5)` in 870, and `x*x*x` from `pow(x, 3)` in
256 583. Excel's `^` is a different runtime; the golden suite absorbs the difference
(worst 8.3e-13 over 75 cases). Consequence for Stage 4/5: rewriting `** 2` as `x*x`,
`** 0.5` as `sqrt`, or `** 3` as repeated multiplication — which Numba does for
integer-literal exponents — is a measurable change (≈1 ulp per operation, ~1e6 steps);
it must be judged against the recorded tolerance, not assumed bit-identical. Likewise
`math.pi` for the 15-digit literal (§1.1).

**e. Return-array convention.** `resultArray(1 To outMax·2)` is returned as a length
`outMax·2 + 1` array with element 0 unused (module header; py 498, 868). Not numeric, but
any API consumer must know it; a Stage 2 wrapper should strip it.

### 3.2 VBA behaviours the port preserves that DEVIATIONS.md does not list

Each is a candidate row with status "preserved". None is a port error.

**a. `vAv` sums `2N + 1` cells and divides by `2N − 1`.** VBA 797-802 (×4): seed
`arrayA(1, N)`, then `arrayA(1, n)` and `arrayB(1, n)` for `n = 0 … N−1` → `1 + 2N`
terms; divisor `2·pipeSegQTY − 1`. Port identical (py 1011-1015 etc.). Flagged by the
port-reviewer as well. Effect: `vAv` is biased by `(2N+1)/(2N−1)` ≈ 1.004 for N = 546.

**b. The force ramp covers `s − 1` sub-steps of an `s`-sub-step sample.** VBA 422 etc.:
`k/(s−1)` reaches the next sample at `k = s−1`; the next sample's `k = 0` repeats that
value, so every sample value is held for two consecutive sub-steps. The waveform is right
at sample boundaries (no cumulative drift) but 1/`s` of each interval is a plateau. D-7
records only the `s = 1` division by zero.

**c. Parity index discontinuity at phase boundaries** (JC only; details in §2.5). Only
the 2→3 boundary is unconditional; it requires phase 3 to run (§4).

**d. Friction dead-zone.** `sign(v, 0.000001)` (VBA 428 etc.): with `fricAcc <= |v| <
1e-6` the Coulomb term is dropped for that sub-step. For the golden inputs
`fricAcc = 4.85e-7` (lumped), so the window `[4.85e-7, 1e-6)` exists and is crossed at
every velocity zero-crossing; the effect is tiny but it is a modelling quirk, not a
threshold on `fricAcc`.

**e. Phase 3 threshold is on `x²` and in absolute units** (§1.1, `0.01`). For the golden
inputs it never triggers; with zero damping and friction and `|x| > 0.1` the loop does not
terminate (NOTES.md).

**f. `GetPressureResponse` simulates `2·closureTime`** with `outMax + 1` samples at
`2·timeStep` spacing (VBA 206, 243-245), and truncates the pipe to `outMax` half-cells
(VBA 207). Neither is stated in the VBA interface comments.

### 3.3 Reviewer observations on process (no code change implied)

* `pyproject.toml` `addopts` deselects both golden markers, so the CLAUDE.md gate
  `pytest -q` never runs the Excel oracle; NOTES.md names `pytest -m slow` as the Stage 2
  gate. CLAUDE.md should say so (left for the owner; this review makes no code or config
  change).
* `legacy/vba/Existing Code.bas` was changed once (commit da022b8, `floor` fix) by the
  owner; the workbook's `Module1` carries the same fix (re-verified by the reviewer with
  `olevba`), so the fixtures and the source agree.

---

## 4. Behaviours the golden suite does not exercise

The suite (`tests/test_golden.py`, fixtures `curve_10in`) runs 75 `GetPeakResponse` cases
and holds 3 never-run `GetPeakResponseJC` cases, all with: one force column (25135 × 1),
`stepQTY = 40`, `sampleFreq = 1265.13`, `celerity = 1237`, `dampingPercent = 0.5`,
`restrainFreqRatio = 1`, `gap = 0.002`, `outputType = 0`, `dynamicFric ∈ {0.005, 1e-6}`,
`physicalLength ∈ {3, 6, 12, 24, 48}`, `natFreq ∈ 2 … 24`. Derived per span:

| L (m) | `unb` | `CLng(unb)` | `kOverlap` | phase-1 exit (`totInd`, `k`) |
|---|---|---|---|---|
| 3 | 3.068 | 3 | 3 | 4, 2 |
| 6 | 6.136 | 6 | 5 | 7, 5 |
| 12 | 12.273 | 12 | 11 | 13, 10 |
| 24 (JC) | 24.546 | 25 | 22 | 25, 21 |
| 48 | 49.091 | 49 | 4 | 50, 3 |

Where a row says "smoke/structure only", `tests/test_smoke.py` or `test_structure.py`
runs the path (shape, finiteness, an identity) but no Excel value pins it.

**Entry points and output types**

1. `GetPressureResponse` — no golden case at all (smoke only: runs, 1-D ≡ column, 2-D
   pattern runs, short-pipe segment count, multi-column ≡ flattened). Unpinned within it:
   the fully-closed branch `closure >= 0.999999999` (VBA 270-273), the pump ramp with
   `pumpRampPressure ≠ 0` (smoke uses 2 bar, no reference), whether either friction clamp
   (`0.9`, `0.9·rhoC`, D-6) ever saturates, the `outMax < L/(c·dt)` truncation (VBA 207),
   `velAtPump = 0`.
2. `GetPeakResponseJC` — fixtures exist, never run (hours in pure Python). Until Stage 5
   the whole MoC block (§2.5), `dF`, `dacayFactor`, `vAv`, the fluid-corrected mass /
   stiffness / damping / fricAcc (VBA 726-729) and the `mass ≠ total mass` friction
   correction are unverified against Excel. Structure tests pin only `fluidArea = 0 ≡
   lumped` and "fluid coupling changes the answer".
3. `outputType = 1, 2, 3` (time histories) — never compared with Excel for either solver.
   The golden suite checks five scalars per case, and with `restrainFreqRatio = 1` the
   static-equivalent force is `xMax·stiffness` and `FMax` depends only on the force column
   and the delay, so effectively **three** numbers (`xMax`, `vMax`, `aMax`) per case. An
   off-by-one in `resultArray(totInd)` or a wrong phase-3 guard would pass.
   (Smoke: histories run and their peak equals the summary `xMax`.)

**Branches inside the peak solvers**

4. `useUndamped = True` (VBA 803-818, ×4): a compile-time constant, dead in VBA and in the
   port; cannot be reached without editing the source. Indices were desk-checked only.
5. The short-span fallback `pipeSegQTY − 2·pivotSegQTY <= 2` (VBA 736-740): golden JC
   spans give N − 2·pivot ≥ 492. Smoke only.
6. Bilinear restraint: with `restrainFreqRatio = 1` the term
   `minUnsigned(gap, x) + max(0, |x| − gap)·sign(x)·ratio²` equals `x` identically, so
   `gap` has no numerical effect in any golden case (structure test
   `gap = 0 & ratio = 1 ≡ gap = 1e9` confirms). `ratio ≠ 1`, and hence the gap, the
   `minUnsigned` ladder and the `max(0, …)` clamp, are structure-tested only ("engaged
   gap changes the answer").
7. Phase 3 (free decay, VBA 568-608 / 1108-1203): never entered. Largest golden
   `max_displacement` is 3.62e-3 m, `x² <= 2.4e-5 < 0.01`. Everything in it — the
   `xZero` reset, the `totInd <= outMax·2` guard, the `k = 1 To s` parity shift (§2.5),
   the non-terminating zero-damping case — is unpinned.
8. Zero damping (`dampingPercent = 0`) and zero friction: structure test only
   (undamped midline = F/k within 1 %).
9. Sticking branch `Abs(v) < fricAcc` (VBA 425-426): exercised in the lumped cases only
   around velocity zero-crossings (`fricAcc = 4.85e-7` m/s per sub-step against
   `vMax ≈ 1e-3 … 1e-2`); in the JC cases `dynamicFric = 1e-6` makes `fricAcc ≈ 1e-10`,
   so sticking occurs only at `v = 0` exactly (the first sub-step).
10. `stepQTY ≠ 40`: no other value against Excel. In particular `stepQTY = 1` (D-7,
    smoke raises), odd `stepQTY` (changes the MoC parity bookkeeping, §2.5), and
    `kOverlap ∈ {0, stepQTY}` (empty k-loop A or B) are unpinned; golden `kOverlap ∈
    {3, 4, 5, 11, 22}`.
11. `CLng` ties (`x.5`): no golden quantity lands on a tie (`unb`, `unb·s` fractions above
    are not .5), so round-half-to-even vs half-up is untested by the oracle
    (`test_vba_compat.py` pins it directly).
12. Multi-column `forceHistory` (`U2 > 1`): every golden input is one column, so the
    wrap branches `i + 1 > U1 And j < U2` (VBA 414-416, 476-478, 483-485, 517-519,
    523-525 and JC twins), the `jB > U2` clamp in phase 1 (407-409; phase 1 exits in
    column 1 after ≤ 50 samples) and the post-phase-1 re-base (468-471) are never taken.
    Structure test: 2-D ≡ column-major flattening (both solvers, output 0 and 1).
13. 1-D input (`AddDimension` path, VBA 368-369): golden passes `(n, 1)`; smoke pins
    1-D ≡ column. The D-5 row-count quirk cannot manifest from numpy.
14. D-8 (single-row history → subscript out of range): smoke raises; no Excel `#VALUE!`
    fixture.
15. D-9 (`On Error GoTo ErrFound` swallowing): no fixture with an Excel `#VALUE!`
    result; the port raises instead.
16. `solvePoly`: all golden calls converge in 35-56 iterations; the 100-iteration cap and
    the `errorVal/varA` division (`varA = 0` ⇔ `EI = 0`) are unexercised. The complex
    seed (§3.1-a) is unexercised and non-physical.
17. `interpFractionB(3)` (D-4) is numerically active in the JC cases (`pivotSegQTY ∈
    {27, 50, 87}`, contributing `((3−4)/(pivot−4))²`), but with `pivotSegQTY = 4` it
    divides by zero — smoke/helper test only.
18. Different `celerity`, `sampleFreq`, `massPerUnitLen`, `EI`, `fluidDensty`,
    `fluidArea`: single values each. Any refactor that changes how these enter
    (`dacayFactor`, cell counts, `unb`) has one data point.

---

## 5. Summary for the Stage 2–5 plan

* No port-vs-VBA correctness discrepancy found by either pass on the paths the oracle
  covers; §3.1 lists five documented-but-unrecorded differences (error paths, overflow,
  `pow`, array convention) and §3.2 six preserved VBA behaviours worth DEVIATIONS rows.
* The refactor units are: one SDOF step (8 copies), one force interpolation (6), one
  index walk (5 + 1), one MoC step (4 identical copies), two pressure half-loops; plus the
  shared set-up between the two peak solvers.
* The oracle is narrow: one force, one `stepQTY`, `ratio = 1`, `outputType = 0`, phase 3
  never entered, JC never run, `GetPressureResponse` absent. A refactor that touches
  phase 3, the gap model, multi-column walks, histories or the pressure solver needs new
  Excel fixtures (or a pinned Stage-1 baseline from `legacy_port.py`) before it can be
  called behaviour-preserving.
