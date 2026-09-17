from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path


class ChatRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            return self._open_connection()
        except sqlite3.OperationalError:
            self._cleanup_stale_files()
            return self._open_connection()

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=MEMORY")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _cleanup_stale_files(self) -> None:
        journal_path = self.db_path.with_name(f"{self.db_path.name}-journal")

        if self.db_path.exists() and self.db_path.stat().st_size == 0:
            try:
                self.db_path.unlink(missing_ok=True)
            except PermissionError:
                pass

        if journal_path.exists():
            try:
                journal_path.unlink(missing_ok=True)
            except PermissionError:
                pass

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_files()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    password_hash TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    nickname TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (room_id) REFERENCES rooms (id)
                );
                """
            )
            room_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(rooms)").fetchall()
            }
            if "password_hash" not in room_columns:
                connection.execute(
                    "ALTER TABLE rooms ADD COLUMN password_hash TEXT"
                )
            connection.commit()

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _serialize_room(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None

        room = dict(row)
        room["is_private"] = bool(room.pop("password_hash", None))
        return room

    def list_rooms(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    r.id,
                    r.name,
                    r.password_hash,
                    r.created_at,
                    COUNT(m.id) AS message_count
                FROM rooms r
                LEFT JOIN messages m ON m.room_id = r.id
                GROUP BY r.id
                ORDER BY r.id DESC
                """
            ).fetchall()

        return [self._serialize_room(row) for row in rows if row is not None]

    def create_room(self, name: str, password: str | None = None) -> dict:
        normalized_name = " ".join(name.split()).strip()
        if not normalized_name:
            raise ValueError("Room name is required.")

        normalized_password = (password or "").strip()
        password_hash = (
            self._hash_password(normalized_password) if normalized_password else None
        )

        with self._lock:
            try:
                with self._connect() as connection:
                    cursor = connection.execute(
                        "INSERT INTO rooms (name, password_hash) VALUES (?, ?)",
                        (normalized_name, password_hash),
                    )
                    connection.commit()
                    room_id = cursor.lastrowid
            except sqlite3.IntegrityError as exc:
                raise ValueError("A room with the same name already exists.") from exc

        room = self.get_room(room_id)
        if room is None:
            raise ValueError("Failed to create room.")
        return room

    def get_room(self, room_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    r.id,
                    r.name,
                    r.password_hash,
                    r.created_at,
                    COUNT(m.id) AS message_count
                FROM rooms r
                LEFT JOIN messages m ON m.room_id = r.id
                WHERE r.id = ?
                GROUP BY r.id
                """,
                (room_id,),
            ).fetchone()

        return self._serialize_room(row)

    def verify_room_password(self, room_id: int, password: str | None = None) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM rooms WHERE id = ?",
                (room_id,),
            ).fetchone()

        if row is None:
            return False

        password_hash = row["password_hash"]
        if not password_hash:
            return True

        normalized_password = (password or "").strip()
        if not normalized_password:
            return False

        return self._hash_password(normalized_password) == password_hash

    def delete_room(self, room_id: int) -> bool:
        with self._lock:
            with self._connect() as connection:
                connection.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
                cursor = connection.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
                connection.commit()

        return cursor.rowcount > 0

    def save_message(
        self,
        room_id: int,
        event_type: str,
        message: str,
        nickname: str | None = None,
    ) -> dict:
        normalized_message = message.strip()
        if not normalized_message:
            raise ValueError("Message is required.")

        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO messages (room_id, event_type, nickname, message)
                    VALUES (?, ?, ?, ?)
                    """,
                    (room_id, event_type, nickname, normalized_message),
                )
                connection.commit()
                message_id = cursor.lastrowid

                row = connection.execute(
                    """
                    SELECT id, room_id, event_type, nickname, message, created_at
                    FROM messages
                    WHERE id = ?
                    """,
                    (message_id,),
                ).fetchone()

        if row is None:
            raise ValueError("Failed to save message.")
        return dict(row)

    def list_messages(self, room_id: int, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, room_id, event_type, nickname, message, created_at
                FROM messages
                WHERE room_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (room_id, limit),
            ).fetchall()

        return [dict(row) for row in reversed(rows)]
