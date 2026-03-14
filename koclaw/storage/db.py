import calendar
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, path: str | Path):
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                title      TEXT    NOT NULL,
                run_at     DATETIME NOT NULL,
                recurrence TEXT    DEFAULT NULL,
                notified   INTEGER  DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type TEXT    NOT NULL,
                scope_id   TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(scope_type, scope_id)
            );

            CREATE TABLE IF NOT EXISTS session_summaries (
                session_id TEXT    PRIMARY KEY,
                content    TEXT    NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS computer_use_containers (
                session_id   TEXT PRIMARY KEY,
                container_id TEXT NOT NULL,
                vnc_port     INTEGER NOT NULL,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # 마이그레이션
        for migration in [
            "ALTER TABLE scheduled_tasks ADD COLUMN recurrence TEXT DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN slack_ts TEXT DEFAULT NULL",
            "UPDATE messages SET session_id = 'slack:' || session_id WHERE session_id NOT LIKE 'slack:%' AND session_id NOT LIKE 'discord:%'",
            "UPDATE scheduled_tasks SET session_id = 'slack:' || session_id WHERE session_id NOT LIKE 'slack:%' AND session_id NOT LIKE 'discord:%'",
        ]:
            try:
                await self._conn.execute(migration)
            except Exception:
                pass
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self._conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ── Messages ─────────────────────────────────────────────────────────

    async def save_message(self, session_id: str, role: str, content: str) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_last_message_id(self, session_id: str) -> int | None:
        rows = await self.fetch_all(
            "SELECT id FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        return rows[0]["id"] if rows else None

    async def update_message_slack_ts(self, msg_id: int, slack_ts: str) -> None:
        await self._conn.execute(
            "UPDATE messages SET slack_ts = ? WHERE id = ?",
            (slack_ts, msg_id),
        )
        await self._conn.commit()

    async def delete_message_pair_by_slack_ts(self, slack_ts: str) -> bool:
        rows = await self.fetch_all(
            "SELECT id, session_id FROM messages WHERE slack_ts = ?", (slack_ts,)
        )
        if not rows:
            return False
        asst_id = rows[0]["id"]
        session_id = rows[0]["session_id"]
        # assistant 메시지 및 바로 이전 user 메시지 삭제
        await self._conn.execute(
            """DELETE FROM messages WHERE id = ?
               OR (session_id = ? AND role = 'user'
                   AND id = (SELECT MAX(id) FROM messages
                              WHERE session_id = ? AND id < ? AND role = 'user'))""",
            (asst_id, session_id, session_id, asst_id),
        )
        await self._conn.commit()
        return True

    async def get_messages(self, session_id: str, limit: int | None = None) -> list[dict]:
        sql = """
            SELECT role, content, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
        """
        rows = await self.fetch_all(sql, (session_id,))
        if limit:
            rows = rows[-limit:]
        return rows

    # ── Scheduled Tasks ───────────────────────────────────────────────────

    async def save_task(
        self, session_id: str, title: str, run_at: str, recurrence: str | None = None
    ) -> None:
        await self._conn.execute(
            "INSERT INTO scheduled_tasks (session_id, title, run_at, recurrence) VALUES (?, ?, ?, ?)",
            (session_id, title, run_at, recurrence),
        )
        await self._conn.commit()

    async def get_pending_tasks(self) -> list[dict]:
        return await self.fetch_all("SELECT * FROM scheduled_tasks WHERE notified = 0")

    async def get_due_tasks(self) -> list[dict]:
        return await self.fetch_all(
            "SELECT * FROM scheduled_tasks WHERE notified = 0 AND run_at <= datetime('now', 'localtime')"
        )

    async def mark_task_notified(self, task_id: int) -> None:
        await self._conn.execute(
            "UPDATE scheduled_tasks SET notified = 1 WHERE id = ?",
            (task_id,),
        )
        await self._conn.commit()

    async def update_task_run_at(self, session_id: str, title: str, run_at: str) -> bool:
        cursor = await self._conn.execute(
            "UPDATE scheduled_tasks SET run_at = ? "
            "WHERE session_id = ? AND title = ? AND notified = 0",
            (run_at, session_id, title),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def advance_task_run_at(self, task_id: int, recurrence: str) -> None:
        rows = await self.fetch_all("SELECT run_at FROM scheduled_tasks WHERE id = ?", (task_id,))
        current = datetime.fromisoformat(rows[0]["run_at"])
        if recurrence == "hourly":
            next_run = current + timedelta(hours=1)
        elif recurrence == "daily":
            next_run = current + timedelta(days=1)
        elif recurrence == "weekly":
            next_run = current + timedelta(weeks=1)
        elif recurrence == "monthly":
            month = current.month % 12 + 1
            year = current.year + (1 if current.month == 12 else 0)
            day = min(current.day, calendar.monthrange(year, month)[1])
            next_run = current.replace(year=year, month=month, day=day)
        else:
            return
        await self._conn.execute(
            "UPDATE scheduled_tasks SET run_at = ? WHERE id = ?",
            (next_run.strftime("%Y-%m-%d %H:%M:%S"), task_id),
        )
        await self._conn.commit()

    async def delete_task(self, session_id: str, title: str) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM scheduled_tasks WHERE session_id = ? AND title = ?",
            (session_id, title),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ── Memories ──────────────────────────────────────────────────────────────

    async def save_memory(self, scope_type: str, scope_id: str, content: str) -> None:
        await self._conn.execute(
            """INSERT INTO memories (scope_type, scope_id, content, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(scope_type, scope_id) DO UPDATE SET
                   content = excluded.content,
                   updated_at = CURRENT_TIMESTAMP""",
            (scope_type, scope_id, content),
        )
        await self._conn.commit()

    async def get_memory(self, scope_type: str, scope_id: str) -> str | None:
        rows = await self.fetch_all(
            "SELECT content FROM memories WHERE scope_type = ? AND scope_id = ?",
            (scope_type, scope_id),
        )
        return rows[0]["content"] if rows else None

    async def delete_memory(self, scope_type: str, scope_id: str) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM memories WHERE scope_type = ? AND scope_id = ?",
            (scope_type, scope_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ── Session Summaries ─────────────────────────────────────────────────────

    async def save_summary(self, session_id: str, content: str) -> None:
        await self._conn.execute(
            """INSERT INTO session_summaries (session_id, content, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(session_id) DO UPDATE SET
                   content = excluded.content,
                   updated_at = CURRENT_TIMESTAMP""",
            (session_id, content),
        )
        await self._conn.commit()

    async def get_summary(self, session_id: str) -> str | None:
        rows = await self.fetch_all(
            "SELECT content FROM session_summaries WHERE session_id = ?",
            (session_id,),
        )
        return rows[0]["content"] if rows else None

    async def count_messages(self, session_id: str) -> int:
        rows = await self.fetch_all(
            "SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ?",
            (session_id,),
        )
        return rows[0]["cnt"]

    # ── Computer Use Containers ───────────────────────────────────────────────

    async def save_container(self, session_id: str, container_id: str, vnc_port: int) -> None:
        await self._conn.execute(
            """INSERT INTO computer_use_containers (session_id, container_id, vnc_port)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   container_id = excluded.container_id,
                   vnc_port = excluded.vnc_port,
                   created_at = CURRENT_TIMESTAMP""",
            (session_id, container_id, vnc_port),
        )
        await self._conn.commit()

    async def get_all_containers(self) -> list[dict]:
        return await self.fetch_all(
            "SELECT session_id, container_id, vnc_port FROM computer_use_containers"
        )

    async def delete_container(self, session_id: str) -> None:
        await self._conn.execute(
            "DELETE FROM computer_use_containers WHERE session_id = ?", (session_id,)
        )
        await self._conn.commit()

    async def delete_old_messages(self, session_id: str, keep_last: int) -> None:
        await self._conn.execute(
            """DELETE FROM messages
               WHERE session_id = ?
               AND id NOT IN (
                   SELECT id FROM messages
                   WHERE session_id = ?
                   ORDER BY id DESC
                   LIMIT ?
               )""",
            (session_id, session_id, keep_last),
        )
        await self._conn.commit()
