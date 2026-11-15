"""Per-agent SQLite event memory; weights remain frozen."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Memory:
    def __init__(self, path: Path | str, max_per_agent: int = 80, max_age: int = 200):
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS memories (agent TEXT NOT NULL, tick INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)")
        self.db.execute("CREATE INDEX IF NOT EXISTS memory_lookup ON memories(agent,tick)")
        self.max_per_agent, self.max_age = max_per_agent, max_age

    def add(self, agent: str, tick: int, kind: str, payload: dict[str, Any]) -> None:
        if not agent.startswith("prey-") or len(kind) > 30:
            raise ValueError("invalid memory namespace or kind")
        compact = json.dumps(payload, separators=(",", ":"))
        if len(compact) > 1200:
            compact = json.dumps({"truncated": True, "preview": compact[:900]})
        self.db.execute("INSERT INTO memories VALUES (?,?,?,?)", (agent, tick, kind, compact))
        self.db.execute("DELETE FROM memories WHERE agent=? AND tick<?", (agent, tick - self.max_age))
        self.db.execute("DELETE FROM memories WHERE rowid IN (SELECT rowid FROM memories WHERE agent=? ORDER BY tick DESC,rowid DESC LIMIT -1 OFFSET ?)", (agent, self.max_per_agent))
        self.db.commit()

    def retrieve(self, agent: str, tick: int, kinds: tuple[str, ...] = (), limit: int = 4) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT tick,kind,payload FROM memories WHERE agent=? AND tick>=? ORDER BY tick DESC,rowid DESC LIMIT ?",
                               (agent, tick - self.max_age, self.max_per_agent)).fetchall()
        if kinds:
            rows.sort(key=lambda row: (row[1] in kinds, row[0]), reverse=True)
        return [{"tick": t, "kind": k, "payload": json.loads(p)} for t, k, p in rows[:limit]]

    def close(self) -> None:
        self.db.close()


class NullMemory:
    def add(self, *args: object) -> None:
        pass

    def retrieve(self, *args: object, **kwargs: object) -> list[dict[str, Any]]:
        return []

    def close(self) -> None:
        pass
