"""Conversation memory.

* **Short-term**: the last N turns of a session (question + final answer
  only – never raw tool payloads, which would bloat context and cost).
* **Long-term preferences**: durable facts a planner states once
  ("our target service level is 98%"), extracted deterministically and
  applied as tool defaults on later turns.

SQLite keeps it zero-ops; the interface maps to Redis/Postgres for a
multi-replica deployment (sessions must not be pinned to a pod).
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SL = re.compile(r"(?:target|our|use)\s+(?:a\s+)?service level\s+(?:is|of|to|at)?\s*(\d{2}(?:\.\d+)?)\s*%", re.I)


class Memory:
    def __init__(self, path: Path | str = ":memory:", max_turns: int = 6) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self.max_turns = max_turns
        with self._lock:
            self._con.executescript(
                """
                CREATE TABLE IF NOT EXISTS turns(session_id TEXT, ts REAL, question TEXT, answer TEXT);
                CREATE INDEX IF NOT EXISTS ix_turns ON turns(session_id, ts);
                CREATE TABLE IF NOT EXISTS prefs(session_id TEXT, key TEXT, value TEXT,
                                                 PRIMARY KEY(session_id, key));
                """
            )

    def history(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._con.execute(
                "SELECT question, answer FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT ?",
                (session_id, self.max_turns),
            ).fetchall()
        msgs: list[dict[str, Any]] = []
        for q, a in reversed(rows):
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        return msgs

    def append(self, session_id: str, question: str, answer: str) -> None:
        with self._lock:
            self._con.execute("INSERT INTO turns VALUES (?,?,?,?)", (session_id, time.time(), question, answer))
            self._con.commit()

    def learn(self, session_id: str, question: str) -> dict[str, str]:
        learned = {}
        m = _SL.search(question)
        if m:
            learned["service_level"] = str(float(m.group(1)) / 100)
        with self._lock:
            for k, v in learned.items():
                self._con.execute("INSERT OR REPLACE INTO prefs VALUES (?,?,?)", (session_id, k, v))
            self._con.commit()
        return learned

    def prefs(self, session_id: str) -> dict[str, str]:
        with self._lock:
            rows = self._con.execute("SELECT key, value FROM prefs WHERE session_id=?", (session_id,)).fetchall()
        return dict(rows)
