---
name: golden
description: Run the golden-master suite against Excel fixtures and report max relative/absolute error per case. Invoke with /golden.
disable-model-invocation: true
---
Run `pytest -q tests/test_golden.py -p no:cacheprovider --tb=short`. Then run `python tools/golden_report.py` and paste its table (case id, output name, max |rel err|, max |abs err|, status). If any case fails, list the first failing sample index and the two values. Do not modify any file.
