"""Shared pytest configuration for surge_sdof."""

import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pytest_terminal_summary(terminalreporter):
    """Say how the review's supporting-code checks compared, when they ran: the history
    documents are compared exactly or at a tolerance depending on numpy's kernel, and
    that choice must never pass unnoticed (``tests/test_review_support.py``)."""
    support = sys.modules.get("test_review_support")
    for line in getattr(support, "REPORT", ()):
        terminalreporter.write_line(f"review support: {line}")
