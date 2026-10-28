"""Run every rule over a set of migrations and score the result."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .rules import (
    RULES,
    SEVERITY_ORDER,
    SEVERITY_WEIGHT,
    Finding,
    analyse,
    sort_findings,
)
from .scanner import Migration, build, discover, duplicate_versions, relative_name


class LintError(ValueError):
    """Raised when there is nothing sensible to lint."""


@dataclass(frozen=True)
class LintResult:
    root: Path
    migrations: tuple[Migration, ...]
    findings: tuple[Finding, ...]
    score: int
    grade: str
    counts: dict[str, int]

    @property
    def files(self) -> int:
        return len(self.migrations)

    @property
    def statements(self) -> int:
        return sum(len(migration.statements) for migration in self.migrations)

    def at_or_above(self, severity: str) -> list[Finding]:
        if severity not in SEVERITY_ORDER:
            raise ValueError(f"unknown severity: {severity}")
        limit = SEVERITY_ORDER[severity]
        return [item for item in self.findings if SEVERITY_ORDER[item.severity] <= limit]

    def should_fail(self, fail_on: str) -> bool:
        if fail_on == "never":
            return False
        return bool(self.at_or_above(fail_on))


def lint_directory(directory: str | Path) -> LintResult:
    root = Path(directory)
    try:
        migrations = discover(root)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise LintError(str(exc)) from exc
    if not migrations:
        raise LintError(f"no .sql files found under {root}")
    return lint_migrations(migrations, root)


def lint_files(paths: list[str | Path]) -> LintResult:
    files = [Path(path) for path in paths]
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise LintError(f"file not found: {', '.join(missing)}")
    migrations = discover_files(files)
    if not migrations:
        raise LintError("no .sql files given")
    root = Path(_common_root(files))
    return lint_migrations(migrations, root)


def discover_files(paths: list[Path]) -> list[Migration]:
    migrations = [build(path) for path in sorted(paths, key=lambda item: item.name)]
    migrations.sort(key=lambda item: (item.version is None, item.version or 0, item.name))
    return migrations


def lint_migrations(migrations: list[Migration], root: Path) -> LintResult:
    findings: list[Finding] = []
    for migration in migrations:
        findings.extend(analyse(migration, relative_name(root, migration.path)))

    for version, group in duplicate_versions(migrations).items():
        for migration in group:
            findings.append(
                Finding(
                    code="duplicate-version",
                    severity=RULES["duplicate-version"].severity,
                    file=relative_name(root, migration.path),
                    line=1,
                    message=f"version {version} is also used by "
                    + ", ".join(
                        other.path.name for other in group if other.path is not migration
                    ),
                    statement=migration.filename,
                )
            )

    ordered = sort_findings(findings)
    score = min(100, sum(SEVERITY_WEIGHT[item.severity] for item in ordered))
    counts = {severity: 0 for severity in SEVERITY_ORDER}
    for item in ordered:
        counts[item.severity] += 1
    return LintResult(
        root=root,
        migrations=tuple(migrations),
        findings=tuple(ordered),
        score=score,
        grade=grade_for(score),
        counts=counts,
    )


def grade_for(score: int) -> str:
    if score == 0:
        return "A"
    if score < 15:
        return "B"
    if score < 40:
        return "C"
    if score < 70:
        return "D"
    return "F"


def _common_root(files: list[Path]) -> Path:
    parents = [path.resolve().parent for path in files]
    try:
        from os.path import commonpath

        return Path(commonpath([str(parent) for parent in parents]))
    except ValueError:
        return parents[0]
