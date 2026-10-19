"""Smoke test: the package imports and exposes a version."""

import surge_sdof


def test_package_imports():
    assert isinstance(surge_sdof.__version__, str)
