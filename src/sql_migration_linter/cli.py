"""Command line entry point for ``migration-lint``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .lint import LintError, lint_directory, lint_files
from .report import render_json, render_markdown, render_text
from .rules import RULES

SEVERITIES = ("low", "medium", "high", "critical")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migration-lint",
        description="Static risk review of SQL migration files.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="lint a migrations directory or explicit files")
    lint.add_argument("--dir", help="directory searched recursively for *.sql")
    lint.add_argument("--file", action="append", default=[], help="lint one file (repeatable)")
    lint.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    lint.add_argument(
        "--fail-on",
        choices=("never",) + SEVERITIES,
        default="high",
        help="exit 1 when a finding at or above this severity exists (default: high)",
    )

    rules = sub.add_parser("rules", help="list every rule")
    rules.add_argument("--format", choices=("text", "markdown"), default="text")

    explain = sub.add_parser("explain", help="explain one rule")
    explain.add_argument("code")

    scan = sub.add_parser("scan", help="list migrations in apply order")
    scan.add_argument("--dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "rules":
        if args.format == "markdown":
            print("| Code | Severity | Rule | Fix |")
            print("| --- | --- | --- | --- |")
            for rule in RULES.values():
                print(f"| `{rule.code}` | {rule.severity} | {rule.title} | {rule.hint} |")
        else:
            for rule in RULES.values():
                print(f"{rule.code:<30} {rule.severity:<9} {rule.title}")
        return 0

    if args.command == "explain":
        rule = RULES.get(args.code)
        if rule is None:
            print(f"unknown rule: {args.code}", file=sys.stderr)
            print("known rules: " + ", ".join(sorted(RULES)), file=sys.stderr)
            return 2
        print(f"{rule.code} ({rule.severity})")
        print(f"  {rule.title}")
        print(f"  why:  {rule.detail}")
        print(f"  fix:  {rule.hint}")
        return 0

    if args.command == "scan":
        try:
            result = lint_directory(args.dir)
        except LintError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for migration in result.migrations:
            version = f"{migration.version:03d}" if migration.version is not None else "---"
            print(
                f"{version}  {migration.filename:<44} "
                f"{len(migration.statements):>3} statements  {migration.line_count:>4} lines"
            )
        return 0

    if args.command == "lint":
        if bool(args.dir) == bool(args.file):
            print("error: pass exactly one of --dir or --file", file=sys.stderr)
            return 2
        try:
            result = (
                lint_directory(args.dir) if args.dir else lint_files(args.file)
            )
        except LintError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if args.format == "json":
            print(render_json(result))
        elif args.format == "markdown":
            print(render_markdown(result))
        else:
            print(render_text(result))
        return 1 if result.should_fail(args.fail_on) else 0

    return 2
