# surge_sdof — developer targets. The interpreter is the project venv (CLAUDE.md: the
# `pytest` on PATH is an isolated tool without numpy).
PY ?= .venv/bin/python

.PHONY: test test-nojit test-both slow golden lint bench clean-cache

# Fast suite under Numba (the default; slow / jc_slow markers are excluded by addopts).
test:
	$(PY) -m pytest -q

# The same source as plain Python: numba.njit returns the undecorated function.
test-nojit:
	NUMBA_DISABLE_JIT=1 $(PY) -m pytest -q

# Both modes, after wiping the Numba on-disk cache: cache=True does not notice when a
# callee in another module changed (moc.step / step_scalars inside _integrate_kernel),
# so a stale cache could pass tests against old compiled code.
test-both: clean-cache test test-nojit

# Lumped golden gate (before any commit touching src/).
slow:
	$(PY) -m pytest -q -m slow

# Every golden case, the three full JC cases included.
golden:
	$(PY) -m pytest -q -m "slow or jc_slow" --durations=0

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

bench:
	$(PY) tools/bench.py

clean-cache:
	find src -name '*.nbi' -delete -o -name '*.nbc' -delete
