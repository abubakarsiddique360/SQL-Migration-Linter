"""Rules, findings and the per-statement checks.

Every rule has a stable code, a severity and a one-line fix. Checks work on *masked* SQL:
string literals have been replaced by spaces, so a comment containing the word DROP cannot
produce a finding, and a table called ``update_flag`` cannot look like an UPDATE statement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .scanner import Migration
from .statements import DDL_KEYWORDS, WRITE_KEYWORDS, Statement, contains_keyword

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEVERITY_WEIGHT = {"critical": 40, "high": 20, "medium": 8, "low": 3}


@dataclass(frozen=True)
class Rule:
    code: str
    severity: str
    title: str
    detail: str
    hint: str


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    file: str
    line: int
    message: str
    statement: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "statement": self.statement,
        }


RULES: dict[str, Rule] = {
    rule.code: rule
    for rule in (
        Rule(
            "destructive-drop-table",
            "critical",
            "DROP TABLE",
            "Dropping a table deletes its data and cannot be rolled back after the migration.",
            "Rename the table, wait for a release, then drop it in a later migration.",
        ),
        Rule(
            "destructive-drop-object",
            "critical",
            "DROP DATABASE or SCHEMA",
            "Dropping a schema or database removes every object inside it.",
            "Never ship this as a migration; run it deliberately by hand.",
        ),
        Rule(
            "destructive-drop-column",
            "high",
            "DROP COLUMN",
            "Dropping a column breaks every reader that still selects it.",
            "Deploy code that stops reading the column first; drop it next release.",
        ),
        Rule(
            "truncate-table",
            "high",
            "TRUNCATE",
            "TRUNCATE empties a table immediately and usually takes an exclusive lock.",
            "Use a DELETE with a WHERE clause and a reviewed predicate instead.",
        ),
        Rule(
            "unbounded-update",
            "critical",
            "UPDATE without WHERE",
            "An UPDATE without a predicate rewrites every row in the table.",
            "Add a WHERE clause, or guard the statement with a row count check.",
        ),
        Rule(
            "unbounded-delete",
            "critical",
            "DELETE without WHERE",
            "A DELETE without a predicate removes every row in the table.",
            "Add a WHERE clause; batch large deletions instead of one statement.",
        ),
        Rule(
            "not-null-without-default",
            "high",
            "ADD COLUMN NOT NULL without DEFAULT",
            "Existing rows cannot satisfy the new constraint, so the migration fails or backfills.",
            "Add the column nullable, backfill in batches, then set NOT NULL.",
        ),
        Rule(
            "blocking-index-build",
            "medium",
            "CREATE INDEX without CONCURRENTLY",
            "A plain index build blocks writes for the duration of the build (PostgreSQL).",
            "Use CREATE INDEX CONCURRENTLY, outside a transaction.",
        ),
        Rule(
            "table-rewrite-alter",
            "medium",
            "ALTER that rewrites or locks the table",
            "Changing a column type, setting NOT NULL, or adding a constraint reads the whole "
            "table.",
            "Split into: new column, backfill, switch reads, drop old column.",
        ),
        Rule(
            "missing-if-not-exists",
            "low",
            "CREATE without IF NOT EXISTS",
            "Re-running a failed migration aborts on the first object that already exists.",
            "Use IF NOT EXISTS (or DROP ... IF EXISTS) so a retry can succeed.",
        ),
        Rule(
            "insert-without-columns",
            "medium",
            "INSERT without a column list",
            "Positional INSERT breaks silently when a column is added or reordered.",
            "Always name the columns being inserted.",
        ),
        Rule(
            "no-transaction",
            "medium",
            "No transaction wrapper",
            "Multiple schema changes without BEGIN/COMMIT leave a half-applied migration on "
            "failure.",
            "Wrap the file in BEGIN; ... COMMIT; (or let the migration tool do it explicitly).",
        ),
        Rule(
            "naming-convention",
            "low",
            "Migration file name",
            "Files must be ordered and greppable: a numeric version, an underscore, a short name.",
            "Rename to 001_description.sql or 001-description.sql.",
        ),
        Rule(
            "duplicate-version",
            "high",
            "Duplicate migration version",
            "Two files share a version, so the applied order depends on the runner's tie breaker.",
            "Renumber one file and re-check the ordering of later migrations.",
        ),
        Rule(
            "empty-migration",
            "low",
            "Empty migration",
            "A file with no statements is either a leftover or a deleted change.",
            "Delete the file or add the change it is supposed to carry.",
        ),
    )
}

TRANSACTION_WORDS = ("BEGIN", "START TRANSACTION", "COMMIT", "ROLLBACK")


def analyse(migration: Migration, file_name: str | None = None) -> list[Finding]:
    name = file_name or migration.filename
    findings: list[Finding] = []
    has_change = False

    for statement in migration.statements:
        if statement.kind in DDL_KEYWORDS or statement.kind in WRITE_KEYWORDS:
            has_change = True
        findings.extend(_check_statement(statement, name))

    if migration.version is None:
        findings.append(
            _finding("naming-convention", name, 1,
                     f"{migration.filename} is not named <version>_<name>.sql",
                     migration.filename)
        )
    elif not migration.statements:
        findings.append(
            _finding("empty-migration", name, 1, migration.filename,
                     "file contains no SQL statements")
        )
    if has_change and not _has_transaction(migration) and not _uses_concurrently(migration):
        findings.append(
            _finding("no-transaction", name, 1, migration.filename,
                     f"{len(migration.statements)} statement(s) without BEGIN/COMMIT")
        )
    return findings


def _uses_concurrently(migration: Migration) -> bool:
    return any("CONCURRENTLY" in statement.upper for statement in migration.statements)


def _has_transaction(migration: Migration) -> bool:
    upper = migration.text.upper()
    has_begin = "BEGIN" in upper or "START TRANSACTION" in upper
    has_end = "COMMIT" in upper or "ROLLBACK" in upper
    return has_begin and has_end


def _check_statement(statement: Statement, file_name: str) -> list[Finding]:
    upper = statement.upper
    findings: list[Finding] = []
    line = statement.line
    snippet = statement.first_words(6)

    if re.search(r"^DROP\s+TABLE\b", upper):
        findings.append(_finding("destructive-drop-table", file_name, line, snippet))
    if re.search(r"^DROP\s+(DATABASE|SCHEMA)\b", upper):
        findings.append(_finding("destructive-drop-object", file_name, line, snippet))
    if re.search(r"^ALTER\s+TABLE\s+\S+\s+DROP\s+COLUMN\b", upper):
        findings.append(_finding("destructive-drop-column", file_name, line, snippet))
    if re.search(r"^TRUNCATE\b", upper):
        findings.append(_finding("truncate-table", file_name, line, snippet))

    if statement.kind == "UPDATE" and not contains_keyword(upper, "WHERE"):
        findings.append(_finding("unbounded-update", file_name, line, snippet))
    if statement.kind == "DELETE" and not contains_keyword(upper, "WHERE"):
        findings.append(_finding("unbounded-delete", file_name, line, snippet))

    if statement.kind == "ALTER" and re.search(r"\bADD\s+COLUMN\b", upper):
        if re.search(r"\bNOT\s+NULL\b", upper) and not re.search(r"\bDEFAULT\b", upper):
            findings.append(_finding("not-null-without-default", file_name, line, snippet))
    if statement.kind == "ALTER" and re.search(
        r"\b(ALTER\s+COLUMN\b.*\b(TYPE|SET\s+NOT\s+NULL)\b|ADD\s+CONSTRAINT\b)", upper
    ):
        findings.append(_finding("table-rewrite-alter", file_name, line, snippet))

    if re.search(r"^CREATE\s+(UNIQUE\s+)?INDEX\b", upper) and "CONCURRENTLY" not in upper:
        findings.append(_finding("blocking-index-build", file_name, line, snippet))

    if re.search(r"^CREATE\s+(TABLE|(UNIQUE\s+)?INDEX)\b", upper) and "IF NOT EXISTS" not in upper:
        findings.append(_finding("missing-if-not-exists", file_name, line, snippet))

    if statement.kind == "INSERT" and re.search(
        r"^INSERT\s+INTO\s+[^\s(]+\s+VALUES\b", upper
    ):
        findings.append(_finding("insert-without-columns", file_name, line, snippet))

    return findings


def _finding(code: str, file_name: str, line: int, statement: str,
             message: str | None = None) -> Finding:
    rule = RULES[code]
    return Finding(
        code=code,
        severity=rule.severity,
        file=file_name,
        line=line,
        message=message or rule.title,
        statement=statement,
    )


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda item: (SEVERITY_ORDER[item.severity], item.file, item.line, item.code),
    )
