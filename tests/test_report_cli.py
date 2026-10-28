import json
from pathlib import Path

import pytest

from sql_migration_linter.cli import main
from sql_migration_linter.lint import lint_directory
from sql_migration_linter.report import render_json, render_markdown, render_text

BAD = """BEGIN;
DROP TABLE customers;
UPDATE users SET active = true;
COMMIT;
"""


@pytest.fixture()
def project(tmp_path: Path):
    (tmp_path / "001_drop.sql").write_text(BAD, encoding="utf-8")
    (tmp_path / "002_index.sql").write_text(
        "CREATE INDEX idx_users_email ON users (email);\n", encoding="utf-8"
    )
    return tmp_path


def test_text_report_lists_severities_and_fixes(project):
    text = render_text(lint_directory(project))
    assert "CRITICAL" in text
    assert "destructive-drop-table" in text
    assert "fix:" in text
    assert "risk" in text


def test_markdown_report_contains_tables(project):
    markdown = render_markdown(lint_directory(project))
    assert markdown.startswith("### SQL migration lint")
    assert "| Severity | File | Line | Rule | Finding |" in markdown
    assert "#### Files in apply order" in markdown
    assert "`destructive-drop-table`" in markdown


def test_json_report_shape(project):
    payload = json.loads(render_json(lint_directory(project)))
    assert payload["grade"]
    assert payload["counts"]["critical"] >= 1
    assert payload["files"][0]["file"] == "001_drop.sql"
    assert {"code", "severity", "file", "line", "message"} <= set(payload["findings"][0])


def test_clean_report_says_so(tmp_path):
    (tmp_path / "001_ok.sql").write_text("BEGIN;\nSELECT 1;\nCOMMIT;", encoding="utf-8")
    assert "No findings" in render_text(lint_directory(tmp_path))


def test_cli_lint_exit_codes(project, capsys):
    assert main(["lint", "--dir", str(project)]) == 1
    assert "CRITICAL" in capsys.readouterr().out
    assert main(["lint", "--dir", str(project), "--fail-on", "never"]) == 0


def test_cli_lint_markdown_and_json(project, capsys):
    assert main(["lint", "--dir", str(project), "--format", "markdown", "--fail-on", "never"]) == 0
    assert "### SQL migration lint" in capsys.readouterr().out
    assert main(["lint", "--dir", str(project), "--format", "json", "--fail-on", "never"]) == 0
    assert json.loads(capsys.readouterr().out)["findings"]


def test_cli_lint_single_file(project, capsys):
    code = main(["lint", "--file", str(project / "002_index.sql"), "--fail-on", "never"])
    assert code == 0
    assert "blocking-index-build" in capsys.readouterr().out


def test_cli_requires_exactly_one_source(project, capsys):
    assert main(["lint"]) == 2
    assert "exactly one" in capsys.readouterr().err
    assert main(["lint", "--dir", str(project), "--file", "x.sql"]) == 2


def test_cli_missing_directory(tmp_path, capsys):
    assert main(["lint", "--dir", str(tmp_path / "absent")]) == 2
    assert "error" in capsys.readouterr().err


def test_cli_rules_listing(capsys):
    assert main(["rules"]) == 0
    output = capsys.readouterr().out
    assert "destructive-drop-table" in output
    assert main(["rules", "--format", "markdown"]) == 0
    assert "| Code | Severity | Rule | Fix |" in capsys.readouterr().out


def test_cli_explain(capsys):
    assert main(["explain", "unbounded-delete"]) == 0
    output = capsys.readouterr().out
    assert "UPDATE" not in output
    assert "why:" in output and "fix:" in output
    assert main(["explain", "nope"]) == 2
    assert "unknown rule" in capsys.readouterr().err


def test_cli_scan(project, capsys):
    assert main(["scan", "--dir", str(project)]) == 0
    output = capsys.readouterr().out
    assert "001_drop.sql" in output
    assert "statements" in output
