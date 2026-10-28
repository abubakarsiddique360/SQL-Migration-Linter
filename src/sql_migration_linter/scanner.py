"""Find migration files and order them the way a migration runner would."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .statements import Statement, split_statements

FILENAME_PATTERN = re.compile(r"^(?P<version>\d+)[_-](?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)\.sql$",
                              re.IGNORECASE)


@dataclass(frozen=True)
class Migration:
    path: Path
    version: int | None
    name: str
    text: str
    statements: tuple[Statement, ...]

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def line_count(self) -> int:
        return self.text.count("\n") + (1 if self.text and not self.text.endswith("\n") else 0)


def discover(directory: str | Path) -> list[Migration]:
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"migrations directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    migrations: list[Migration] = []
    for path in sorted(root.rglob("*.sql")):
        migrations.append(build(path))
    migrations.sort(key=lambda item: (item.version is None, item.version or 0, item.name))
    return migrations


def build(path: Path) -> Migration:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = FILENAME_PATTERN.match(path.name)
    return Migration(
        path=path,
        version=int(match.group("version")) if match else None,
        name=match.group("name") if match else path.stem,
        text=text,
        statements=tuple(split_statements(text)),
    )


def duplicate_versions(migrations: list[Migration]) -> dict[int, list[Migration]]:
    groups: dict[int, list[Migration]] = defaultdict(list)
    for migration in migrations:
        if migration.version is not None:
            groups[migration.version].append(migration)
    return {version: items for version, items in groups.items() if len(items) > 1}


def relative_name(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name
