"""SQL-Migration-Linter: static risk review of a migrations directory."""

from .lint import LintError, LintResult, lint_directory, lint_files
from .rules import RULES, Finding, Rule
from .scanner import Migration, discover
from .statements import Statement, split_statements

__all__ = [
    "RULES",
    "Finding",
    "LintError",
    "LintResult",
    "Migration",
    "Rule",
    "Statement",
    "discover",
    "lint_directory",
    "lint_files",
    "split_statements",
]

__version__ = "1.0.0"
