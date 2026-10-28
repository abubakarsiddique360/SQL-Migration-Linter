"""Render lint results for a terminal, a pull request comment, or a dashboard."""

from __future__ import annotations

import json
from collections import Counter

from .lint import LintResult
from .rules import RULES, SEVERITY_WEIGHT

BADGES = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}

FILE_LEVEL_RULES = {
    "no-transaction",
    "naming-convention",
    "duplicate-version",
    "empty-migration",
}


def _file_summary(result: LintResult) -> list[dict]:
    per_file: dict[str, list] = {}
    for finding in result.findings:
        per_file.setdefault(finding.file, []).append(finding)
    rows = []
    for migration in result.migrations:
        name = _relative(result, migration.path)
        findings = per_file.get(name, [])
        rows.append(
            {
                "file": name,
                "version": migration.version,
                "statements": len(migration.statements),
                "lines": migration.line_count,
                "findings": len(findings),
                "score": min(100, sum(SEVERITY_WEIGHT[f.severity] for f in findings)),
                "severities": dict(Counter(f.severity for f in findings)),
            }
        )
    return rows


def _relative(result: LintResult, path) -> str:
    from .scanner import relative_name

    return relative_name(result.root, path)


def render_text(
    result: LintResult, *, title: str = "SQL migration lint", root_label: str | None = None
) -> str:
    lines = [
        f"{title}: {root_label or result.root}",
        "=" * 78,
        f"files {result.files}   statements {result.statements}   "
        f"findings {len(result.findings)}   risk {result.score}/100 (grade {result.grade})",
    ]
    if result.counts.get("critical") or result.counts.get("high"):
        lines.append(
            f"critical {result.counts['critical']}   high {result.counts['high']}   "
            f"medium {result.counts['medium']}   low {result.counts['low']}"
        )
    if not result.findings:
        lines.append("")
        lines.append("No findings. Every migration is ordered, wrapped and reversible.")
        return "\n".join(lines)

    lines.append("")
    current = None
    for finding in result.findings:
        if finding.severity != current:
            current = finding.severity
            lines.append(f"{BADGES[current]}")
        rule = RULES[finding.code]
        location = f"{finding.file}:{finding.line}"
        lines.append(f"  {location:<48} [{finding.code}]")
        lines.append(f"      {finding.message}")
        if finding.code not in FILE_LEVEL_RULES and finding.statement:
            lines.append(f"      statement: {finding.statement[:88]}")
        lines.append(f"      fix: {rule.hint}")
    return "\n".join(lines)


def render_markdown(result: LintResult, *, title: str = "SQL migration lint") -> str:
    lines = [f"### {title}", ""]
    lines.append(
        f"**Risk {result.score}/100 (grade {result.grade})** - {result.files} files, "
        f"{result.statements} statements, {len(result.findings)} findings "
        f"({result.counts['critical']} critical, {result.counts['high']} high, "
        f"{result.counts['medium']} medium, {result.counts['low']} low)."
    )
    lines.append("")
    lines.append("| Severity | File | Line | Rule | Finding |")
    lines.append("| --- | --- | ---: | --- | --- |")
    for finding in result.findings:
        lines.append(
            f"| {BADGES[finding.severity]} | `{finding.file}` | {finding.line} | "
            f"`{finding.code}` | {finding.message.replace('|', '/')} |"
        )
    if not result.findings:
        lines.append("| - | - | - | - | No findings |")
    lines.append("")
    lines.append("#### Files in apply order")
    lines.append("")
    lines.append("| # | File | Statements | Findings | Risk |")
    lines.append("| ---: | --- | ---: | ---: | ---: |")
    for index, row in enumerate(_file_summary(result), start=1):
        lines.append(
            f"| {index} | `{row['file']}` | {row['statements']} | {row['findings']} | "
            f"{row['score']} |"
        )
    return "\n".join(lines)


def render_json(result: LintResult) -> str:
    return json.dumps(
        {
            "root": str(result.root),
            "score": result.score,
            "grade": result.grade,
            "counts": result.counts,
            "files": _file_summary(result),
            "findings": [finding.as_dict() for finding in result.findings],
        },
        indent=2,
    )
