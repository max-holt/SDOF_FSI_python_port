# Benchmark history

One row per `tools/bench.py` run (median of the timed repeats; `(c)` is the JC case truncated to 2000 samples). `sha` is HEAD when the run started (`-dirty` = uncommitted changes under src/tests/tools), so the commit that adds a row is that sha's child. Details, result digests and profiles are in `<sha>.json` next to this file.

| date (UTC) | sha | python | numpy | numba | NUMBA_DISABLE_JIT | (a) lumped r20 | (b) lumped r80 | (c) jc r96 n2000 | (d) pressure example | (c) us/sub-step | profile |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-21T02:02:19+00:00 | 1adaddd-dirty | 3.13.16 | 2.5.4 | absent | - | 3.090 s | 3.124 s | 141.495 s | 9.28 ms | 1747.2 | yes |
