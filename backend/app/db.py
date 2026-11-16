"""SQLite storage for runs, tasks and events.

One connection is shared by the whole process and is only ever used from the
event loop thread (all routes are async), so no locking is needed. Queries are
tiny, so they are made directly without a thread pool.
"""
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    run_id TEXT NOT NULL REFERENCES runs(id),
    id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    role TEXT NOT NULL,
    instructions TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    output TEXT,
    error TEXT,
    tokens INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL REFERENCES runs(id),
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    ts TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""

SUMMARY_COLUMNS = "id, goal, status, provider, created_at, finished_at, total_tokens"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        # check_same_thread=False: the connection is created in the main thread
        # at startup and then used from the event loop thread.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def _execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self.conn:  # commits on success
            return self.conn.execute(sql, params)

    # runs

    def create_run(self, run_id: str, goal: str, provider: str) -> None:
        self._execute(
            "INSERT INTO runs (id, goal, status, provider, created_at) VALUES (?, ?, 'running', ?, ?)",
            (run_id, goal, provider, now_iso()),
        )

    def update_run(self, run_id: str, **fields) -> None:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        self._execute(f"UPDATE runs SET {assignments} WHERE id = ?", (*fields.values(), run_id))

    def get_run(self, run_id: str):
        """The full Run shape including its tasks, or None if the id is unknown."""
        row = self._execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return {**dict(row), "tasks": self.get_tasks(run_id)}

    def list_runs(self, limit: int = 50) -> list:
        rows = self._execute(
            f"SELECT {SUMMARY_COLUMNS} FROM runs ORDER BY rowid DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in rows]

    def running_run_ids(self) -> list:
        return [row["id"] for row in self._execute("SELECT id FROM runs WHERE status = 'running'")]

    # tasks

    def insert_tasks(self, run_id: str, tasks: list) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT INTO tasks (run_id, id, position, title, role, instructions, depends_on)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (run_id, t["id"], position, t["title"], t["role"], t["instructions"],
                     json.dumps(t["depends_on"]))
                    for position, t in enumerate(tasks)
                ],
            )

    def update_task(self, run_id: str, task_id: str, **fields) -> None:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        self._execute(
            f"UPDATE tasks SET {assignments} WHERE run_id = ? AND id = ?",
            (*fields.values(), run_id, task_id),
        )

    def get_tasks(self, run_id: str) -> list:
        rows = self._execute("SELECT * FROM tasks WHERE run_id = ? ORDER BY position", (run_id,))
        tasks = []
        for row in rows:
            task = dict(row)
            del task["run_id"], task["position"]
            task["depends_on"] = json.loads(task["depends_on"])
            tasks.append(task)
        return tasks

    # events

    def add_event(self, run_id: str, type: str, data: dict) -> dict:
        """Store an event with the next seq for its run and return the Event shape."""
        ts = now_iso()
        with self.conn:
            seq = self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            self.conn.execute(
                "INSERT INTO events (run_id, seq, type, ts, data) VALUES (?, ?, ?, ?, ?)",
                (run_id, seq, type, ts, json.dumps(data)),
            )
        return {"seq": seq, "run_id": run_id, "type": type, "ts": ts, "data": data}

    def events_after(self, run_id: str, after: int = 0) -> list:
        rows = self._execute(
            "SELECT * FROM events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after)
        )
        return [
            {"seq": row["seq"], "run_id": run_id, "type": row["type"], "ts": row["ts"],
             "data": json.loads(row["data"])}
            for row in rows
        ]
