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
