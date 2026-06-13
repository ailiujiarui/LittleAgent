import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from pydantic import BaseModel

from mini_agent.bootstrap import init_workspace
from mini_agent.db.migrations import apply_migrations


CORE_MEMORY_FILES = [
    "SELF.md",
    "MEMORY.md",
    "RECENT_CONTEXT.md",
]
WRITABLE_MEMORY_FILES = {
    "SELF.md",
    "MEMORY.md",
    "RECENT_CONTEXT.md",
    "HISTORY.md",
    "PENDING.md",
}


class PromptBlock(BaseModel):
    name: str
    content: str


class MemoryItem(BaseModel):
    kind: str
    content: str
    keywords: str


class MemoryStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.memory_dir = self.workspace / "memory"
        self.db_path = self.workspace / "agent.db"
        init_workspace(self.workspace)
        apply_migrations(self.db_path)

    def build_prompt_blocks(self, session_key: str, query: str) -> List[PromptBlock]:
        return [
            PromptBlock(name=name, content=self.read_file(name))
            for name in CORE_MEMORY_FILES
        ]

    def read_file(self, name: str) -> str:
        path = self._memory_file(name)
        return path.read_text(encoding="utf-8")

    def write_file(self, name: str, content: str) -> None:
        path = self._memory_file(name)
        path.write_text(content, encoding="utf-8")

    def append_pending(self, content: str, keywords: Iterable[str]) -> None:
        pending_path = self._memory_file("PENDING.md")
        old = pending_path.read_text(encoding="utf-8")
        if old.strip() == "# Pending":
            old = ""
        separator = "" if not old or old.endswith("\n") else "\n"
        pending_path.write_text(f"{old}{separator}{content}\n", encoding="utf-8")
        self._insert_memory_item("pending", content, keywords)

    def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        terms = _keywords(query)
        if not terms:
            return []

        conditions = " or ".join(
            ["lower(content) like ? or lower(keywords) like ?" for _ in terms]
        )
        sql = f"""
            select kind, content, keywords
            from memory_items
            where {conditions}
            order by id desc
            limit ?
        """
        params = []
        for term in terms:
            pattern = f"%{term}%"
            params.extend([pattern, pattern])
        params.append(limit)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            MemoryItem(kind=row[0], content=row[1], keywords=row[2])
            for row in rows
        ]

    def merge_pending(self, merged_content: str) -> Path:
        memory_path = self._memory_file("MEMORY.md")
        backup_dir = self.workspace / "backups" / "memory"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup_path = backup_dir / f"MEMORY.md.{stamp}.bak"
        backup_path.write_text(memory_path.read_text(encoding="utf-8"), encoding="utf-8")

        memory_path.write_text(merged_content, encoding="utf-8")
        self._memory_file("PENDING.md").write_text("", encoding="utf-8")
        return backup_path

    def _insert_memory_item(
        self,
        kind: str,
        content: str,
        keywords: Iterable[str],
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert into memory_items (kind, content, keywords)
                values (?, ?, ?)
                """,
                (kind, content, " ".join(str(keyword) for keyword in keywords)),
            )
            conn.commit()

    def _memory_file(self, name: str) -> Path:
        if name not in WRITABLE_MEMORY_FILES:
            raise ValueError(f"unsupported memory file: {name}")
        return self.memory_dir / name


def _keywords(text: str) -> List[str]:
    return [
        part.lower()
        for part in re.split(r"\W+", text)
        if part.strip()
    ]
