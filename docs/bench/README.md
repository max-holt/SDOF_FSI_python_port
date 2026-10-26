# Benchmark history

One row per `tools/bench.py` run (median of the timed repeats). Cloud containers differ between sessions, so absolute times are not comparable across rows: case (a), the frozen legacy lumped case, is re-run in-session as the reference and every other case is given in seconds and, in brackets, as the ratio of its median to (a)'s. `(c)` and `(g)` are the JC case truncated to 2000 samples through the literal port and through `response.peak_response_jc` (legacy flags); `(e)`/`(f)` are `(a)`/`(b)` through `response.peak_response`; `(h)` is `(d)` through `pressure.pressure_response`; `cells/s` is MoC cell-updates per second (sub-steps x pipeSegQTY / s). `sha` is HEAD when the run started (`-dirty` = uncommitted changes under src/tests/tools), so the commit that adds a row is that sha's child. Details, result digests and profiles are in `<sha>.json` next to this file.

| date (UTC) | sha | python | numpy | numba | NUMBA_DISABLE_JIT | cpu | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | (e) response r20 | (f) response r80 | (g) response_jc r96 n2000 | (h) response_pressure example | (c) us/sub-step | (g) us/sub-step | (c) cells/s | (g) cells/s | profile |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-21T02:02:19+00:00 | 1adaddd-dirty | 3.13.16 | 2.5.4 | absent | - | Intel(R) Xeon(R) Processor @ 2.80GHz | 3.090 s | 3.124 s [1.01] | 141.495 s [45.8] | 9.28 ms [0.003] | - | - | - | - | 1747.2 | - | - | - | yes |
| 2026-10-21T08:19:30+00:00 | 4ea09d2 | 3.13.16 | 2.5.4 | absent | - | Intel(R) Xeon(R) Processor @ 2.80GHz | 3.235 s | 3.107 s [0.96] | 146.834 s [45.4] | 9.89 ms [0.003] | 0.910 s [0.28] | 0.925 s [0.29] | - | - | 1813.2 | - | - | - | yes |
| 2026-10-21T09:50:42+00:00 | 293e507-dirty | 3.13.16 | 2.5.4 | absent | - | Intel(R) Xeon(R) Processor @ 2.80GHz | 3.195 s | 3.132 s [0.98] | 147.042 s [46.03] | 10.71 ms [0.00] | 0.995 s [0.31] | 0.933 s [0.29] | 77.064 s [24.12] | - | 1815.7 | 951.6 | 0.37 M | 0.70 M | yes |
| 2026-10-21T22:34:12+00:00 | 6fa4595 | 3.13.16 | 2.5.4 | absent | - | Intel(R) Xeon(R) Processor @ 2.10GHz | 1.850 s | 2.121 s [1.15] | 101.162 s [54.67] | 6.18 ms [0.00] | 0.809 s [0.44] | 0.803 s [0.43] | 52.626 s [28.44] | 4.70 ms [0.00] | 1249.2 | 649.8 | 0.53 M | 1.02 M | no |
| 2026-10-22T00:20:08+00:00 | 3912479 | 3.13.16 | 2.5.4 | absent | - | Intel(R) Xeon(R) Processor @ 2.10GHz | 2.055 s | 2.131 s [1.04] | 98.324 s [47.85] | 6.20 ms [0.00] | 0.740 s [0.36] | 0.679 s [0.33] | 51.145 s [24.89] | 4.55 ms [0.00] | 1214.1 | 631.6 | 0.55 M | 1.05 M | no |
| 2026-10-22T00:44:44+00:00 | b5fc5c7 | 3.13.16 | 2.5.4 | absent | - | Intel(R) Xeon(R) Processor @ 2.10GHz | 2.042 s | 1.985 s [0.97] | 99.690 s [48.82] | 6.40 ms [0.00] | 0.769 s [0.38] | 0.720 s [0.35] | 51.228 s [25.09] | 7.51 ms [0.00] | 1231.0 | 632.6 | 0.54 M | 1.05 M | yes |

## JC golden suite (`pytest -m jc_slow --durations=0`)

Full `GetPeakResponseJC` golden cases against Excel (25135 samples, stepQTY 40). Not part of `tools/bench.py`. The 484b25e row is the literal port, sequential in one process; the 293e507 row is `response.peak_response_jc` with the legacy flags (`tests/test_differential.py::test_peak_response_jc_matches_excel_on_the_golden_curve`), the three cases as parallel single-case processes on 4 cores (Intel Xeon @ 2.80 GHz), max rel err per case from `tests/.golden_cache/*_response.json`.

| date (UTC) | sha | python | numpy | numba | row 96 (f 3 Hz, N 666) | row 97 (f 7.5 Hz, N 592) | row 98 (f 22 Hz, N 546) | total | max rel err (96 / 97 / 98) | result |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-21 | 484b25e | 3.13.16 | 2.5.4 | absent | 1826.8 s | 1564.5 s | 1411.5 s | 1:20:02 | 8.6e-13 / 2.1e-14 / 8.4e-15 | 3/3 pass at 1e-12; RTOL set to 5e-12 |
| 2026-10-21 | 293e507 | 3.13.16 | 2.5.4 | absent | 969 s | 856 s | 800 s | 16:12 wall (3 in parallel) | 8.6e-13 / 2.1e-14 / 8.4e-15 | 3/3 pass at 5e-12 (`peak_response_jc`, legacy flags) |

## Stage 5 runs (literal -> refactored -> Numba)

One section per `tools/bench.py` run since Stage 5. Rows: the literal port (pure Python), the Stage 4 modules as plain Python (`NUMBA_DISABLE_JIT=1`) and the same modules compiled by Numba (steady state; the first call and the compile are given separately). Every cell is the median of the timed repeats in seconds and, in brackets, the ratio to case (a), the literal lumped r20 case run in the same session. Details in `<sha>.json`.

### 2026-10-22T02:26:41+00:00 · b9597a3-dirty · Intel(R) Xeon(R) Processor @ 2.80GHz · python 3.13.16 · numpy 2.5.4 · numba 0.68.0 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 3.839 s [1.000] | 3.877 s [1.010] | 178.445 s [46.480] | 11.49 ms [0.003] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.332 s [0.347] | 1.237 s [0.322] | 99.121 s [25.818] | 8.32 ms [0.002] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.309 s [0.081] | 0.344 s [0.090] | 0.179 s [0.047] | 8.48 ms [0.002] | 2.132 s [0.555] | 2.079 s [0.541] | 1.937 s [0.505] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 3.362 s; first call per case: response_r20 0.733 s, response_r80 0.309 s, response_jc_r96_n2000 0.174 s, response_pressure_example 8.74 ms, response_jc_r96_full 2.226 s, response_jc_r97_full 2.007 s, response_jc_r98_full 1.834 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.30 M, response_jc_r96_n2000 [python] 0.54 M, response_jc_r96_n2000 [numba] 301.29 M, response_jc_r96_full [numba] 314.31 M, response_jc_r97_full [numba] 286.56 M, response_jc_r98_full [numba] 283.63 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 210 MB, rss_response_jc_r96_full_type1 191 MB.
Digest pairs (refactored == literal): all equal; profile yes.

### 2026-10-22T05:03:46+00:00 · f2f4211 · Intel(R) Xeon(R) Processor @ 2.80GHz · python 3.13.16 · numpy 2.5.4 · numba 0.68.0 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 3.235 s [1.000] | 3.176 s [0.982] | 158.603 s [49.031] | 9.49 ms [0.003] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.107 s [0.342] | 1.116 s [0.345] | 77.216 s [23.871] | 12.80 ms [0.004] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.290 s [0.090] | 0.264 s [0.082] | 0.143 s [0.044] | 7.34 ms [0.002] | 1.792 s [0.554] | 1.649 s [0.510] | 1.541 s [0.476] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.862 s; first call per case: response_r20 0.352 s, response_r80 0.295 s, response_jc_r96_n2000 0.140 s, response_pressure_example 7.13 ms, response_jc_r96_full 1.822 s, response_jc_r97_full 1.841 s, response_jc_r98_full 1.595 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.34 M, response_jc_r96_n2000 [python] 0.70 M, response_jc_r96_n2000 [numba] 377.95 M, response_jc_r96_full [numba] 373.97 M, response_jc_r97_full [numba] 361.37 M, response_jc_r98_full [numba] 356.62 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 191 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-10-26T10:50:14+00:00 · 5bf153b · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.16 · numpy 2.5.4 · numba 0.68.0 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 3.259 s [1.000] | 2.831 s [0.869] | 140.487 s [43.111] | 13.03 ms [0.004] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.095 s [0.336] | 1.084 s [0.333] | 73.422 s [22.531] | 8.52 ms [0.003] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.242 s [0.074] | 0.244 s [0.075] | 0.111 s [0.034] | 5.98 ms [0.002] | 1.445 s [0.444] | 1.305 s [0.400] | 1.234 s [0.379] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.868 s; first call per case: response_r20 0.293 s, response_r80 0.236 s, response_jc_r96_n2000 0.121 s, response_pressure_example 6.20 ms, response_jc_r96_full 1.380 s, response_jc_r97_full 1.232 s, response_jc_r98_full 1.270 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.38 M, response_jc_r96_n2000 [python] 0.73 M, response_jc_r96_n2000 [numba] 485.53 M, response_jc_r96_full [numba] 463.73 M, response_jc_r97_full [numba] 456.70 M, response_jc_r98_full [numba] 445.36 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 191 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

