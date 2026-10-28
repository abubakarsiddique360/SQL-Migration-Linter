from pathlib import Path

import pytest

from sql_migration_linter.lint import LintError, grade_for, lint_directory, lint_files
from sql_migration_linter.rules import RULES, SEVERITY_ORDER, analyse
from sql_migration_linter.scanner import build, discover, duplicate_versions


def make_file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def codes(findings) -> set[str]:
    return {finding.code for finding in findings}


def test_rules_have_consistent_metadata():
    for code, rule in RULES.items():
        assert code == rule.code
        assert rule.severity in SEVERITY_ORDER
        assert rule.hint and rule.title and rule.detail


def test_drop_table_is_critical(tmp_path):
    path = make_file(tmp_path, "001_drop.sql", "DROP TABLE customers;")
    findings = analyse(build(path))
    assert "destructive-drop-table" in codes(findings)
    assert all(f.severity == "critical" for f in findings if f.code == "destructive-drop-table")


def test_drop_database_is_flagged(tmp_path):
    path = make_file(tmp_path, "001_drop.sql", "DROP DATABASE production;")
    assert "destructive-drop-object" in codes(analyse(build(path)))


def test_drop_column(tmp_path):
    path = make_file(tmp_path, "001_alter.sql",
                     "ALTER TABLE users DROP COLUMN email;")
    assert "destructive-drop-column" in codes(analyse(build(path)))


def test_truncate(tmp_path):
    path = make_file(tmp_path, "001_truncate.sql", "TRUNCATE audit_log;")
    assert "truncate-table" in codes(analyse(build(path)))


def test_update_without_where(tmp_path):
    path = make_file(tmp_path, "001_update.sql", "UPDATE users SET active = true;")
    assert "unbounded-update" in codes(analyse(build(path)))


def test_update_with_where_is_clean(tmp_path):
    path = make_file(
        tmp_path, "001_update.sql", "UPDATE users SET active = true WHERE id = 42;"
    )
    assert "unbounded-update" not in codes(analyse(build(path)))


def test_delete_without_where(tmp_path):
    path = make_file(tmp_path, "001_delete.sql", "DELETE FROM sessions;")
    assert "unbounded-delete" in codes(analyse(build(path)))


def test_keyword_inside_string_literal_does_not_trigger(tmp_path):
    path = make_file(
        tmp_path,
        "001_insert.sql",
        "INSERT INTO notes (body) VALUES ('DELETE FROM users');",
    )
    assert "unbounded-delete" not in codes(analyse(build(path)))


def test_not_null_without_default(tmp_path):
    path = make_file(
        tmp_path, "001_alter.sql", "ALTER TABLE users ADD COLUMN team TEXT NOT NULL;"
    )
    assert "not-null-without-default" in codes(analyse(build(path)))


def test_not_null_with_default_is_allowed(tmp_path):
    path = make_file(
        tmp_path,
        "001_alter.sql",
        "ALTER TABLE users ADD COLUMN team TEXT NOT NULL DEFAULT 'core';",
    )
    assert "not-null-without-default" not in codes(analyse(build(path)))


def test_blocking_index(tmp_path):
    path = make_file(tmp_path, "001_index.sql", "CREATE INDEX idx ON users (email);")
    findings = analyse(build(path))
    assert "blocking-index-build" in codes(findings)
    assert "missing-if-not-exists" in codes(findings)


def test_concurrent_index_is_not_blocking(tmp_path):
    path = make_file(
        tmp_path, "001_index.sql", "CREATE INDEX CONCURRENTLY idx ON users (email);"
    )
    findings = analyse(build(path))
    assert "blocking-index-build" not in codes(findings)
    assert "no-transaction" not in codes(findings)


def test_table_rewrite_alter(tmp_path):
    path = make_file(
        tmp_path, "001_alter.sql", "ALTER TABLE users ALTER COLUMN age TYPE bigint;"
    )
    assert "table-rewrite-alter" in codes(analyse(build(path)))


def test_insert_without_columns(tmp_path):
    path = make_file(tmp_path, "001_insert.sql", "INSERT INTO plans VALUES (1, 'free');")
    assert "insert-without-columns" in codes(analyse(build(path)))


def test_insert_with_columns_is_clean(tmp_path):
    path = make_file(
        tmp_path, "001_insert.sql", "INSERT INTO plans (id, name) VALUES (1, 'free');"
    )
    assert "insert-without-columns" not in codes(analyse(build(path)))


def test_transaction_wrapper_is_detected(tmp_path):
    path = make_file(
        tmp_path,
        "001_change.sql",
        "BEGIN;\nUPDATE users SET active = true WHERE id = 1;\nCOMMIT;",
    )
    assert "no-transaction" not in codes(analyse(build(path)))


def test_missing_transaction_is_flagged(tmp_path):
    path = make_file(tmp_path, "001_change.sql", "CREATE TABLE a (id int);")
    assert "no-transaction" in codes(analyse(build(path)))


def test_naming_convention(tmp_path):
    path = make_file(tmp_path, "add_view.sql", "CREATE VIEW v AS SELECT 1;")
    assert "naming-convention" in codes(analyse(build(path)))


def test_duplicate_versions_are_found(tmp_path):
    make_file(tmp_path, "001_a.sql", "SELECT 1;")
    make_file(tmp_path, "001_b.sql", "SELECT 2;")
    make_file(tmp_path, "002_c.sql", "SELECT 3;")
    migrations = discover(tmp_path)
    duplicates = duplicate_versions(migrations)
    assert list(duplicates) == [1]
    assert len(duplicates[1]) == 2


def test_discover_orders_by_version(tmp_path):
    make_file(tmp_path, "010_last.sql", "SELECT 1;")
    make_file(tmp_path, "002_middle.sql", "SELECT 1;")
    make_file(tmp_path, "zzz_unversioned.sql", "SELECT 1;")
    assert [migration.filename for migration in discover(tmp_path)] == [
        "002_middle.sql",
        "010_last.sql",
        "zzz_unversioned.sql",
    ]


def test_discover_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover(tmp_path / "absent")


def test_lint_directory_scores_and_counts(tmp_path):
    make_file(tmp_path, "001_drop.sql", "BEGIN;\nDROP TABLE customers;\nCOMMIT;")
    result = lint_directory(tmp_path)
    assert result.files == 1
    assert result.counts["critical"] == 1
    assert result.score == 40
    assert result.grade == "D"


def test_lint_directory_rejects_empty_directory(tmp_path):
    with pytest.raises(LintError, match="no .sql files"):
        lint_directory(tmp_path)


def test_lint_directory_rejects_missing_directory(tmp_path):
    with pytest.raises(LintError, match="not found"):
        lint_directory(tmp_path / "absent")


def test_lint_files_accepts_explicit_paths(tmp_path):
    first = make_file(tmp_path, "001_a.sql", "SELECT 1;")
    second = make_file(tmp_path, "002_b.sql", "SELECT 2;")
    result = lint_files([first, second])
    assert result.files == 2


def test_lint_files_rejects_missing(tmp_path):
    with pytest.raises(LintError, match="file not found"):
        lint_files([tmp_path / "nope.sql"])


def test_score_is_capped_at_100(tmp_path):
    text = "BEGIN;\n" + "\n".join(["DROP TABLE t;"] * 10) + "\nCOMMIT;"
    make_file(tmp_path, "001_bad.sql", text)
    result = lint_directory(tmp_path)
    assert result.score == 100
    assert result.grade == "F"


def test_fail_thresholds(tmp_path):
    make_file(tmp_path, "001_drop.sql", "BEGIN;\nDROP TABLE t;\nCOMMIT;")
    result = lint_directory(tmp_path)
    assert result.should_fail("critical")
    assert result.should_fail("high")
    assert not result.should_fail("never")
    assert len(result.at_or_above("critical")) == 1


@pytest.mark.parametrize(
    "score,grade",
    [(0, "A"), (3, "B"), (14, "B"), (15, "C"), (39, "C"), (40, "D"), (69, "D"), (70, "F")],
)
def test_grade_boundaries(score, grade):
    assert grade_for(score) == grade


def test_clean_project_has_zero_risk(tmp_path):
    make_file(
        tmp_path,
        "001_clean.sql",
        "BEGIN;\nCREATE TABLE IF NOT EXISTS a (id int);\nCOMMIT;",
    )
    result = lint_directory(tmp_path)
    assert result.findings == ()
    assert result.score == 0
    assert result.grade == "A"
