---
name: golden
description: Run the golden-master suite against Excel fixtures and report max relative/absolute error per case. Invoke with /golden (lumped cases) or /golden --jc (also the 3 junction-coupling cases).
disable-model-invocation: true
---
Run the golden cases. By default the 3 `jc_slow` cases (hours each in pure Python) are deselected:

```
.venv/bin/python -m pytest -q tests/test_golden.py -m "slow or jc_slow" -p no:cacheprovider --tb=short \
  --deselect "tests/test_golden.py::test_golden_peak_response[r096_jc_L24_f3]" \
  --deselect "tests/test_golden.py::test_golden_peak_response[r097_jc_L24_f7.5]" \
  --deselect "tests/test_golden.py::test_golden_peak_response[r098_jc_L24_f22]"
```

If invoked as `/golden --jc`, omit the three `--deselect` options so the JC cases run as well (expect hours; run in the background and report when done).

Then run `.venv/bin/python tools/golden_report.py` and paste its table (case id, output name, max |rel err|, max |abs err|, status). If any case fails, list the first failing sample index and the two values. Do not modify any file.
