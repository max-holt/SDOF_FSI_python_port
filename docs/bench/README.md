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

Cases (d) and (h), the Example-sheet `GetPressureResponse` call through the literal port and through `pressure.pressure_response`, were removed with the pressure solver in review session R.1b; the sections before that keep them as recorded.

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

### 2026-10-27T03:20:47+00:00 · 83d23ef-dirty · Intel(R) Xeon(R) Processor @ 2.30GHz · python 3.13.16 · numpy 2.5.4 · numba 0.68.0 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 1.761 s [1.000] | 1.711 s [0.972] | 83.821 s [47.612] | 5.79 ms [0.003] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.777 s [0.442] | 0.744 s [0.422] | 43.748 s [24.850] | 4.43 ms [0.003] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.171 s [0.097] | 0.174 s [0.099] | 79.51 ms [0.045] | 4.33 ms [0.003] | 1.006 s [0.572] | 0.908 s [0.516] | 0.849 s [0.482] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 1.934 s; first call per case: response_r20 0.200 s, response_r80 0.173 s, response_jc_r96_n2000 77.10 ms, response_pressure_example 4.50 ms, response_jc_r96_full 0.979 s, response_jc_r97_full 0.910 s, response_jc_r98_full 0.839 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.64 M, response_jc_r96_n2000 [python] 1.23 M, response_jc_r96_n2000 [numba] 678.30 M, response_jc_r96_full [numba] 665.93 M, response_jc_r97_full [numba] 655.97 M, response_jc_r98_full [numba] 647.06 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 192 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-10-29T01:01:10+00:00 · 028e399 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.16 · numpy 2.5.4 · numba 0.68.0 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.627 s [1.000] | 2.562 s [0.975] | 128.905 s [49.066] | 7.62 ms [0.003] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.078 s [0.410] | 1.115 s [0.424] | 67.395 s [25.654] | 5.75 ms [0.002] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.255 s [0.097] | 0.242 s [0.092] | 0.107 s [0.041] | 5.69 ms [0.002] | 1.379 s [0.525] | 1.282 s [0.488] | 1.176 s [0.448] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.876 s; first call per case: response_r20 0.625 s, response_r80 0.264 s, response_jc_r96_n2000 0.108 s, response_pressure_example 5.99 ms, response_jc_r96_full 1.367 s, response_jc_r97_full 1.220 s, response_jc_r98_full 1.185 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.42 M, response_jc_r96_n2000 [python] 0.80 M, response_jc_r96_n2000 [numba] 503.56 M, response_jc_r96_full [numba] 485.98 M, response_jc_r97_full [numba] 464.70 M, response_jc_r98_full [numba] 467.26 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 191 MB, rss_response_jc_r96_full_type1 191 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-10-29T05:10:16+00:00 · 3664dc7 · 13th Gen Intel(R) Core(TM) i5-13600KF · python 3.14.3 · numpy 2.5.4 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 1.915 s [1.000] | 1.931 s [1.008] | 94.421 s [49.306] | 5.88 ms [0.003] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.792 s [0.414] | 0.789 s [0.412] | 46.936 s [24.510] | 4.14 ms [0.002] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.172 s [0.090] | 0.171 s [0.089] | 69.47 ms [0.036] | 4.17 ms [0.002] | 0.811 s [0.423] | 0.728 s [0.380] | 0.691 s [0.361] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 1.384 s; first call per case: response_r20 0.176 s, response_r80 0.172 s, response_jc_r96_n2000 68.36 ms, response_pressure_example 4.25 ms, response_jc_r96_full 0.796 s, response_jc_r97_full 0.729 s, response_jc_r98_full 0.699 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.57 M, response_jc_r96_n2000 [python] 1.15 M, response_jc_r96_n2000 [numba] 776.35 M, response_jc_r96_full [numba] 826.81 M, response_jc_r97_full [numba] 818.55 M, response_jc_r98_full [numba] 795.05 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 233 MB, rss_response_jc_r96_full_type1 233 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-16T04:36:09+00:00 · afead1d · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 1.964 s [1.000] | 1.923 s [0.979] | 94.626 s [48.181] | 5.95 ms [0.003] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.686 s [0.349] | 0.705 s [0.359] | 48.828 s [24.862] | 4.97 ms [0.003] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.190 s [0.097] | 0.203 s [0.103] | 91.03 ms [0.046] | 4.75 ms [0.002] | 1.177 s [0.599] | 1.113 s [0.567] | 0.977 s [0.497] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.175 s; first call per case: response_r20 0.212 s, response_r80 0.277 s, response_jc_r96_n2000 94.50 ms, response_pressure_example 5.06 ms, response_jc_r96_full 1.170 s, response_jc_r97_full 1.061 s, response_jc_r98_full 0.893 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.57 M, response_jc_r96_n2000 [python] 1.10 M, response_jc_r96_n2000 [numba] 592.51 M, response_jc_r96_full [numba] 569.45 M, response_jc_r97_full [numba] 535.25 M, response_jc_r98_full [numba] 562.41 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 243 MB, rss_response_jc_r96_full_type1 243 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-16T05:53:31+00:00 · 253210a · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.036 s [1.000] | 2.077 s [1.020] | 95.494 s [46.896] | 5.99 ms [0.003] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.732 s [0.360] | 0.705 s [0.346] | 51.076 s [25.082] | 3.86 ms [0.002] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.184 s [0.090] | 0.190 s [0.093] | 89.08 ms [0.044] | 4.60 ms [0.002] | 1.177 s [0.578] | 1.085 s [0.533] | 0.988 s [0.485] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.226 s; first call per case: response_r20 0.199 s, response_r80 0.188 s, response_jc_r96_n2000 0.102 s, response_pressure_example 4.59 ms, response_jc_r96_full 1.142 s, response_jc_r97_full 0.975 s, response_jc_r98_full 0.939 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.56 M, response_jc_r96_n2000 [python] 1.06 M, response_jc_r96_n2000 [numba] 605.45 M, response_jc_r96_full [numba] 569.65 M, response_jc_r97_full [numba] 549.03 M, response_jc_r98_full [numba] 556.04 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 193 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-23T05:51:03+00:00 · 64b171d · Intel(R) Xeon(R) Processor @ 2.30GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 1.650 s [1.000] | 1.813 s [1.099] | 86.351 s [52.339] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.643 s [0.390] | 0.615 s [0.373] | 46.372 s [28.107] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.178 s [0.108] | 0.171 s [0.104] | 78.26 ms [0.047] | 1.091 s [0.661] | 0.934 s [0.566] | 0.850 s [0.515] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.211 s; first call per case: response_r20 0.178 s, response_r80 0.190 s, response_jc_r96_n2000 78.89 ms, response_jc_r96_full 1.034 s, response_jc_r97_full 0.969 s, response_jc_r98_full 0.947 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.62 M, response_jc_r96_n2000 [python] 1.16 M, response_jc_r96_n2000 [numba] 689.17 M, response_jc_r96_full [numba] 614.11 M, response_jc_r97_full [numba] 638.08 M, response_jc_r98_full [numba] 646.62 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 192 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-23T07:56:10+00:00 · b92e840 · Intel(R) Xeon(R) Processor @ 2.30GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 1.662 s [1.000] | 1.787 s [1.075] | 89.236 s [53.678] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.658 s [0.396] | 0.710 s [0.427] | 46.816 s [28.161] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.246 s [0.148] | 0.217 s [0.131] | 83.87 ms [0.051] | 1.059 s [0.637] | 1.063 s [0.640] | 0.868 s [0.522] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.438 s; first call per case: response_r20 0.191 s, response_r80 0.217 s, response_jc_r96_n2000 84.30 ms, response_jc_r96_full 1.119 s, response_jc_r97_full 0.917 s, response_jc_r98_full 0.845 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.60 M, response_jc_r96_n2000 [python] 1.15 M, response_jc_r96_n2000 [numba] 643.05 M, response_jc_r96_full [numba] 632.92 M, response_jc_r97_full [numba] 560.23 M, response_jc_r98_full [numba] 633.00 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 192 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-23T23:28:59+00:00 · 9dd2f4b · Intel(R) Xeon(R) Processor @ 2.30GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 1.661 s [1.000] | 1.672 s [1.006] | 81.718 s [49.188] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.620 s [0.373] | 0.634 s [0.382] | 44.548 s [26.814] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.166 s [0.100] | 0.165 s [0.099] | 91.69 ms [0.055] | 1.011 s [0.608] | 0.893 s [0.538] | 0.891 s [0.536] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 1.840 s; first call per case: response_r20 0.169 s, response_r80 0.165 s, response_jc_r96_n2000 80.31 ms, response_jc_r96_full 1.010 s, response_jc_r97_full 0.881 s, response_jc_r98_full 0.843 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.66 M, response_jc_r96_n2000 [python] 1.21 M, response_jc_r96_n2000 [numba] 588.19 M, response_jc_r96_full [numba] 663.21 M, response_jc_r97_full [numba] 667.00 M, response_jc_r98_full [numba] 616.94 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 192 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T02:37:45+00:00 · 213e3ef · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.086 s [1.000] | 2.216 s [1.062] | 109.342 s [52.417] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.765 s [0.367] | 0.747 s [0.358] | 58.791 s [28.184] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.204 s [0.098] | 0.200 s [0.096] | 96.32 ms [0.046] | 1.194 s [0.572] | 1.063 s [0.509] | 1.044 s [0.500] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.240 s; first call per case: response_r20 0.204 s, response_r80 0.198 s, response_jc_r96_n2000 0.103 s, response_jc_r96_full 1.196 s, response_jc_r97_full 1.085 s, response_jc_r98_full 1.034 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.49 M, response_jc_r96_n2000 [python] 0.92 M, response_jc_r96_n2000 [numba] 559.94 M, response_jc_r96_full [numba] 561.41 M, response_jc_r97_full [numba] 560.65 M, response_jc_r98_full [numba] 526.45 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 192 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T03:11:54+00:00 · a1c1724 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.212 s [1.000] | 2.180 s [0.986] | 105.696 s [47.784] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.800 s [0.361] | 0.847 s [0.383] | 56.513 s [25.549] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.200 s [0.091] | 0.200 s [0.090] | 0.102 s [0.046] | 1.188 s [0.537] | 1.040 s [0.470] | 0.977 s [0.442] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.297 s; first call per case: response_r20 0.205 s, response_r80 0.200 s, response_jc_r96_n2000 92.77 ms, response_jc_r96_full 1.181 s, response_jc_r97_full 1.084 s, response_jc_r98_full 0.987 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.51 M, response_jc_r96_n2000 [python] 0.95 M, response_jc_r96_n2000 [numba] 531.35 M, response_jc_r96_full [numba] 563.99 M, response_jc_r97_full [numba] 572.85 M, response_jc_r98_full [numba] 562.32 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 228 MB, rss_response_jc_r96_full_type1 192 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T04:51:05+00:00 · f2f11d5 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.195 s [1.000] | 2.377 s [1.083] | 128.265 s [58.445] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.953 s [0.434] | 0.978 s [0.446] | 68.645 s [31.278] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.267 s [0.121] | 0.234 s [0.107] | 0.107 s [0.049] | 1.466 s [0.668] | 1.254 s [0.572] | 1.214 s [0.553] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.143 s; first call per case: response_r20 0.247 s, response_r80 0.290 s, response_jc_r96_n2000 0.109 s, response_jc_r96_full 1.413 s, response_jc_r97_full 1.312 s, response_jc_r98_full 1.230 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.42 M, response_jc_r96_n2000 [python] 0.79 M, response_jc_r96_n2000 [numba] 505.31 M, response_jc_r96_full [numba] 457.27 M, response_jc_r97_full [numba] 475.04 M, response_jc_r98_full [numba] 452.71 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 227 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T05:39:30+00:00 · 1eeb6d4 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.434 s [1.000] | 2.302 s [0.946] | 116.649 s [47.923] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.014 s [0.416] | 0.928 s [0.381] | 64.178 s [26.366] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.241 s [0.099] | 0.239 s [0.098] | 0.106 s [0.044] | 1.244 s [0.511] | 1.186 s [0.487] | 1.085 s [0.446] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.327 s; first call per case: response_r20 0.278 s, response_r80 0.242 s, response_jc_r96_n2000 0.110 s, response_jc_r96_full 1.361 s, response_jc_r97_full 1.153 s, response_jc_r98_full 1.060 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.46 M, response_jc_r96_n2000 [python] 0.84 M, response_jc_r96_n2000 [numba] 507.71 M, response_jc_r96_full [numba] 538.89 M, response_jc_r97_full [numba] 502.25 M, response_jc_r98_full [numba] 506.25 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 193 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T06:04:26+00:00 · bfeb003 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.280 s [1.000] | 2.307 s [1.012] | 114.967 s [50.414] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 0.948 s [0.416] | 0.878 s [0.385] | 64.384 s [28.233] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.227 s [0.099] | 0.223 s [0.098] | 0.101 s [0.044] | 1.174 s [0.515] | 1.074 s [0.471] | 1.089 s [0.477] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.090 s; first call per case: response_r20 0.221 s, response_r80 0.231 s, response_jc_r96_n2000 93.03 ms, response_jc_r96_full 1.208 s, response_jc_r97_full 1.051 s, response_jc_r98_full 1.017 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.47 M, response_jc_r96_n2000 [python] 0.84 M, response_jc_r96_n2000 [numba] 534.64 M, response_jc_r96_full [numba] 570.88 M, response_jc_r97_full [numba] 554.87 M, response_jc_r98_full [numba] 504.75 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 226 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T06:21:07+00:00 · 6ea80ba · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.347 s [1.000] | 2.302 s [0.981] | 119.956 s [51.117] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.726 s [0.735] | 1.550 s [0.661] | 63.235 s [26.946] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.420 s [0.179] | 0.404 s [0.172] | 0.119 s [0.051] | 1.477 s [0.629] | 1.330 s [0.567] | 1.208 s [0.515] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.107 s; first call per case: response_r20 0.444 s, response_r80 0.435 s, response_jc_r96_n2000 0.112 s, response_jc_r96_full 1.470 s, response_jc_r97_full 1.525 s, response_jc_r98_full 1.190 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.45 M, response_jc_r96_n2000 [python] 0.85 M, response_jc_r96_n2000 [numba] 453.16 M, response_jc_r96_full [numba] 453.75 M, response_jc_r97_full [numba] 447.82 M, response_jc_r98_full [numba] 454.76 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 226 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T06:48:20+00:00 · 256522a · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.264 s [1.000] | 2.377 s [1.050] | 113.125 s [49.971] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.249 s [0.552] | 1.315 s [0.581] | 64.511 s [28.497] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.213 s [0.094] | 0.208 s [0.092] | 97.58 ms [0.043] | 1.273 s [0.562] | 1.216 s [0.537] | 1.034 s [0.457] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.280 s; first call per case: response_r20 0.219 s, response_r80 0.211 s, response_jc_r96_n2000 96.21 ms, response_jc_r96_full 1.253 s, response_jc_r97_full 1.251 s, response_jc_r98_full 1.184 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.48 M, response_jc_r96_n2000 [python] 0.84 M, response_jc_r96_n2000 [numba] 552.71 M, response_jc_r96_full [numba] 526.50 M, response_jc_r97_full [numba] 490.08 M, response_jc_r98_full [numba] 531.41 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 228 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T07:06:41+00:00 · 0d1b15c · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.400 s [1.000] | 2.204 s [0.918] | 128.336 s [53.468] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.242 s [0.518] | 1.393 s [0.581] | 63.640 s [26.514] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.216 s [0.090] | 0.217 s [0.090] | 96.61 ms [0.040] | 1.260 s [0.525] | 1.125 s [0.469] | 1.183 s [0.493] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.016 s; first call per case: response_r20 0.221 s, response_r80 0.215 s, response_jc_r96_n2000 0.114 s, response_jc_r96_full 1.362 s, response_jc_r97_full 1.133 s, response_jc_r98_full 1.060 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.42 M, response_jc_r96_n2000 [python] 0.85 M, response_jc_r96_n2000 [numba] 558.27 M, response_jc_r96_full [numba] 531.96 M, response_jc_r97_full [numba] 529.77 M, response_jc_r98_full [numba] 464.52 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 228 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T07:24:19+00:00 · 1634342 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.331 s [1.000] | 2.167 s [0.930] | 112.209 s [48.146] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.359 s [0.583] | 1.370 s [0.588] | 61.596 s [26.429] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.217 s [0.093] | 0.206 s [0.088] | 94.83 ms [0.041] | 1.214 s [0.521] | 1.123 s [0.482] | 1.047 s [0.449] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.045 s; first call per case: response_r20 0.222 s, response_r80 0.214 s, response_jc_r96_n2000 94.56 ms, response_jc_r96_full 1.261 s, response_jc_r97_full 1.136 s, response_jc_r98_full 1.064 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.48 M, response_jc_r96_n2000 [python] 0.88 M, response_jc_r96_n2000 [numba] 568.72 M, response_jc_r96_full [numba] 552.17 M, response_jc_r97_full [numba] 530.29 M, response_jc_r98_full [numba] 524.83 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 230 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T07:46:15+00:00 · 2c239e4 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.230 s [1.000] | 2.257 s [1.012] | 114.740 s [51.451] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.352 s [0.606] | 1.315 s [0.590] | 63.774 s [28.597] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.224 s [0.101] | 0.234 s [0.105] | 95.08 ms [0.043] | 1.274 s [0.572] | 1.199 s [0.538] | 1.152 s [0.516] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.255 s; first call per case: response_r20 0.226 s, response_r80 0.243 s, response_jc_r96_n2000 0.100 s, response_jc_r96_full 1.247 s, response_jc_r97_full 1.196 s, response_jc_r98_full 1.286 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.47 M, response_jc_r96_n2000 [python] 0.85 M, response_jc_r96_n2000 [numba] 567.27 M, response_jc_r96_full [numba] 525.91 M, response_jc_r97_full [numba] 496.85 M, response_jc_r98_full [numba] 477.02 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 231 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T08:02:59+00:00 · c6abb02 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.266 s [1.000] | 2.216 s [0.978] | 114.979 s [50.748] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.365 s [0.603] | 1.434 s [0.633] | 66.750 s [29.461] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.214 s [0.094] | 0.219 s [0.097] | 93.22 ms [0.041] | 1.271 s [0.561] | 1.170 s [0.516] | 1.119 s [0.494] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.301 s; first call per case: response_r20 0.210 s, response_r80 0.211 s, response_jc_r96_n2000 95.09 ms, response_jc_r96_full 1.299 s, response_jc_r97_full 1.123 s, response_jc_r98_full 1.042 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.47 M, response_jc_r96_n2000 [python] 0.81 M, response_jc_r96_n2000 [numba] 578.57 M, response_jc_r96_full [numba] 527.32 M, response_jc_r97_full [numba] 509.09 M, response_jc_r98_full [numba] 491.15 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 233 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

### 2026-11-24T08:30:58+00:00 · f0bade5 · Intel(R) Xeon(R) Processor @ 2.10GHz · python 3.13.18 · numpy 2.5.5 · numba 0.68.1 · llvmlite 0.50.0

| implementation | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | jc r96 full | jc r97 full | jc r98 full |
|---|---|---|---|---|---|---|
| literal (`legacy_port`, pure Python) | 2.327 s [1.000] | 2.347 s [1.009] | 122.679 s [52.712] | - | - | - |
| refactored (Stage 4 modules, `NUMBA_DISABLE_JIT=1`) | 1.430 s [0.615] | 1.471 s [0.632] | 69.855 s [30.015] | - | - | - |
| Numba (Stage 5 `njit`, steady state) | 0.246 s [0.106] | 0.249 s [0.107] | 0.116 s [0.050] | 1.438 s [0.618] | 1.333 s [0.573] | 1.138 s [0.489] |

Numba compile (first call of the Example lumped case in a fresh `NUMBA_CACHE_DIR`): 2.930 s; first call per case: response_r20 0.247 s, response_r80 0.277 s, response_jc_r96_n2000 0.112 s, response_jc_r96_full 1.471 s, response_jc_r97_full 1.316 s, response_jc_r98_full 1.171 s.
MoC cell-updates/s: jc_r96_n2000 [literal] 0.44 M, response_jc_r96_n2000 [python] 0.77 M, response_jc_r96_n2000 [numba] 466.09 M, response_jc_r96_full [numba] 466.13 M, response_jc_r97_full [numba] 447.04 M, response_jc_r98_full [numba] 482.84 M.
Full JC cases vs Excel, max rel err: response_jc_r96_full [numba] 8.6e-13, response_jc_r97_full [numba] 2.1e-14, response_jc_r98_full [numba] 8.4e-15.
Peak RSS, `outputType = 1` on the full history under Numba: rss_response_r20_type1 233 MB, rss_response_jc_r96_full_type1 193 MB.
Digest pairs (refactored == literal): all equal; profile no.

