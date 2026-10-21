# Benchmark history

One row per `tools/bench.py` run (median of the timed repeats; `(c)` is the JC case truncated to 2000 samples; `(e)`/`(f)` are `(a)`/`(b)` through the Stage 4 `response.peak_response`, added 2026-10-21). `sha` is HEAD when the run started (`-dirty` = uncommitted changes under src/tests/tools), so the commit that adds a row is that sha's child. Details, result digests and profiles are in `<sha>.json` next to this file.

| date (UTC) | sha | python | numpy | numba | NUMBA_DISABLE_JIT | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | (c) us/sub-step | profile | (e) response r20 | (f) response r80 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-21T02:02:19+00:00 | 1adaddd-dirty | 3.13.16 | 2.5.4 | absent | - | 3.090 s | 3.124 s | 141.495 s | 9.28 ms | 1747.2 | yes | - | - |

## JC golden suite (`pytest -m jc_slow --durations=0`)

Full `GetPeakResponseJC` golden cases against Excel (25135 samples, stepQTY 40); sequential, one process. Not part of `tools/bench.py`.

| date (UTC) | sha | python | numpy | numba | row 96 (f 3 Hz, N 666) | row 97 (f 7.5 Hz, N 592) | row 98 (f 22 Hz, N 546) | total | max rel err (96 / 97 / 98) | result |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-21 | 484b25e | 3.13.16 | 2.5.4 | absent | 1826.8 s | 1564.5 s | 1411.5 s | 1:20:02 | 8.6e-13 / 2.1e-14 / 8.4e-15 | 3/3 pass at 1e-12; RTOL set to 5e-12 |
| 2026-10-21T08:19:30+00:00 | 4ea09d2 | 3.13.16 | 2.5.4 | absent | - | 3.235 s | 3.107 s | 146.834 s | 9.89 ms | 1813.2 | yes | 0.910 s | 0.925 s |
