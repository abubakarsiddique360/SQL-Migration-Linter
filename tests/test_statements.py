
from sql_migration_linter.statements import contains_keyword, split_statements


def test_splits_on_semicolons_and_tracks_lines():
    sql = "CREATE TABLE a (id int);\n\nINSERT INTO a VALUES (1);\n"
    statements = split_statements(sql)
    assert [statement.kind for statement in statements] == ["CREATE", "INSERT"]
    assert statements[0].line == 1
    assert statements[1].line == 3


def test_ignores_line_comments():
    sql = "-- DROP TABLE customers;\nSELECT 1;"
    statements = split_statements(sql)
    assert len(statements) == 1
    assert statements[0].text == "SELECT 1"
    assert statements[0].line == 2


def test_ignores_block_comments_across_lines():
    sql = "/*\nDROP TABLE customers;\nDELETE FROM audit_log;\n*/\nSELECT 1;"
    statements = split_statements(sql)
    assert len(statements) == 1
    assert statements[0].text == "SELECT 1"


def test_semicolon_inside_string_is_not_a_boundary():
    sql = "INSERT INTO notes VALUES ('a; b', 'it''s fine');\nUPDATE notes SET body = 'x;y';"
    statements = split_statements(sql)
    assert len(statements) == 2
    assert "'a; b'" in statements[0].text


def test_double_quoted_identifier_with_semicolon():
    sql = 'ALTER TABLE "weird;name" ADD COLUMN x int;'
    assert len(split_statements(sql)) == 1


def test_masked_text_hides_literals():
    sql = "UPDATE notes SET body = 'DELETE FROM notes' WHERE id = 1;"
    statement = split_statements(sql)[0]
    assert "DELETE" in statement.text.upper()
    assert "DELETE" not in statement.masked.upper()


def test_line_numbers_inside_multiline_statements():
    sql = "CREATE TABLE a (\n  id int\n);\nDELETE FROM a;"
    statements = split_statements(sql)
    assert statements[0].line == 1
    assert statements[1].line == 4


def test_statement_without_trailing_semicolon_is_kept():
    statements = split_statements("SELECT 1")
    assert len(statements) == 1


def test_trailing_semicolons_do_not_emit_empty_statements():
    assert split_statements(";\n;\n") == []


def test_contains_keyword_is_whole_word_and_case_insensitive():
    assert contains_keyword("delete from t where id = 1", "WHERE")
    assert not contains_keyword("SELECT where_clause FROM t", "WHERE")


def test_escaped_quotes_do_not_end_the_string():
    statements = split_statements("INSERT INTO t VALUES ('it\\'s');SELECT 2;")
    assert len(statements) == 2
