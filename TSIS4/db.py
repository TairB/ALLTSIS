from __future__ import annotations

from pathlib import Path
from typing import Any
import os

try:
    import psycopg2
except ModuleNotFoundError:  # pragma: no cover - depends on local env
    psycopg2 = None

from config import DEFAULT_DB_CONFIG, SCHEMA_FILE


class DatabaseManager:
    def __init__(self, schema_path: Path | None = None) -> None:
        self.schema_path = schema_path or SCHEMA_FILE
        self.available = False
        self.status_message = "Database not initialized."
        self.last_error = ""
        self.database_url = os.getenv("DATABASE_URL")

    def _connect(self):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed.")
        if self.database_url:
            return psycopg2.connect(self.database_url, connect_timeout=3)
        return psycopg2.connect(connect_timeout=3, **DEFAULT_DB_CONFIG)

    def init_schema(self) -> None:
        try:
            schema_sql = self.schema_path.read_text(encoding="utf-8")
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(schema_sql)
            self.available = True
            self.status_message = "Database connected."
            self.last_error = ""
        except Exception as error:  # pragma: no cover - depends on local DB
            self.available = False
            self.last_error = str(error)
            self.status_message = "Database unavailable."

    def _ensure_player(self, cursor, username: str) -> int:
        cursor.execute(
            """
            INSERT INTO players (username)
            VALUES (%s)
            ON CONFLICT (username)
            DO UPDATE SET username = EXCLUDED.username
            RETURNING id
            """,
            (username,),
        )
        return cursor.fetchone()[0]

    def save_session(self, username: str, score: int, level_reached: int) -> bool:
        if not self.available:
            return False
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    player_id = self._ensure_player(cursor, username)
                    cursor.execute(
                        """
                        INSERT INTO game_sessions (player_id, score, level_reached)
                        VALUES (%s, %s, %s)
                        """,
                        (player_id, score, level_reached),
                    )
            return True
        except Exception as error:  # pragma: no cover - depends on local DB
            self.available = False
            self.last_error = str(error)
            self.status_message = "Database unavailable."
            return False

    def get_personal_best(self, username: str) -> int:
        if not self.available or not username:
            return 0
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COALESCE(MAX(gs.score), 0)
                        FROM game_sessions gs
                        JOIN players p ON p.id = gs.player_id
                        WHERE p.username = %s
                        """,
                        (username,),
                    )
                    result = cursor.fetchone()
                    return int(result[0] or 0)
        except Exception as error:  # pragma: no cover - depends on local DB
            self.available = False
            self.last_error = str(error)
            self.status_message = "Database unavailable."
            return 0

    def get_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.available:
            return []
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            p.username,
                            gs.score,
                            gs.level_reached,
                            gs.played_at
                        FROM game_sessions gs
                        JOIN players p ON p.id = gs.player_id
                        ORDER BY gs.score DESC, gs.level_reached DESC, gs.played_at ASC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    rows = cursor.fetchall()
            return [
                {
                    "username": row[0],
                    "score": row[1],
                    "level_reached": row[2],
                    "played_at": row[3],
                }
                for row in rows
            ]
        except Exception as error:  # pragma: no cover - depends on local DB
            self.available = False
            self.last_error = str(error)
            self.status_message = "Database unavailable."
            return []
