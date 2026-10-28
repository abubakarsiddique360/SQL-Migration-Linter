"""Split a migration file into statements without being fooled by strings or comments.

Line numbers point at the first non-blank character of a statement, which is what an editor
needs; they stay correct because the scanner only ever advances one character at a time and
counts newlines inside literals and comments too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Statement kinds that change schema, and therefore deserve a transaction.
DDL_KEYWORDS = {
    "ALTER",
    "COMMENT",
    "CREATE",
    "DROP",
    "GRANT",
    "RENAME",
    "REVOKE",
    "TRUNCATE",
}
WRITE_KEYWORDS = {"DELETE", "INSERT", "MERGE", "UPDATE"}


@dataclass(frozen=True)
class Statement:
    text: str
    line: int
    kind: str
    masked: str

    @property
    def upper(self) -> str:
        return self.masked.upper()

    def first_words(self, count: int = 4) -> str:
        words = self.text.split()
        return " ".join(words[:count])


def split_statements(sql: str) -> list[Statement]:
    """Return the statements in ``sql`` with their source line numbers."""
    statements: list[Statement] = []
    buffer: list[str] = []
    masked: list[str] = []
    line = 1
    start_line: int | None = None
    index = 0
    length = len(sql)

    def flush() -> None:
        nonlocal buffer, masked, start_line
        text = "".join(buffer).strip()
        if text:
            statements.append(
                Statement(
                    text=text,
                    line=start_line or line,
                    kind=(text.split()[0].upper() if text.split() else ""),
                    masked="".join(masked).strip(),
                )
            )
        buffer = []
        masked = []
        start_line = None

    while index < length:
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < length else ""

        if char == "-" and nxt == "-":
            while index < length and sql[index] != "\n":
                index += 1
            continue

        if char == "/" and nxt == "*":
            index += 2
            while index < length and not (sql[index] == "*" and sql[index + 1 : index + 2] == "/"):
                if sql[index] == "\n":
                    line += 1
                index += 1
            index += 2
            continue

        if char in ("'", '"'):
            quote = char
            if start_line is None:
                start_line = line
            buffer.append(char)
            masked.append(" ")
            index += 1
            while index < length:
                current = sql[index]
                if current == "\\" and quote == "'" and index + 1 < length:
                    buffer.extend([current, sql[index + 1]])
                    masked.extend([" ", " "])
                    if sql[index + 1] == "\n":
                        line += 1
                    index += 2
                    continue
                if current == quote:
                    if index + 1 < length and sql[index + 1] == quote:
                        buffer.extend([current, current])
                        masked.extend([" ", " "])
                        index += 2
                        continue
                    buffer.append(current)
                    masked.append(" ")
                    index += 1
                    break
                if current == "\n":
                    line += 1
                buffer.append(current)
                masked.append(" ")
                index += 1
            continue

        if char == ";":
            flush()
            index += 1
            continue

        if char == "\n":
            line += 1
            if buffer:
                buffer.append(char)
                masked.append(char)
            index += 1
            continue

        if start_line is None and not char.isspace():
            start_line = line
        if buffer or not char.isspace():
            buffer.append(char)
            masked.append(char)
        index += 1

    flush()
    return statements


def contains_keyword(masked: str, keyword: str) -> bool:
    """Whole-word, case-insensitive search on already-masked SQL."""
    return re.search(rf"\b{re.escape(keyword)}\b", masked, flags=re.IGNORECASE) is not None
