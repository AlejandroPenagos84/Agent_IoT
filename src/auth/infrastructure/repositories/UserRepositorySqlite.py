import sqlite3
from datetime import datetime

from auth.domain.user import User, UserStatus
from auth.infrastructure.errors import RecordNotFound, sqlite_errors


class UserRepositorySQLite:
    def __init__(self, db_connection: sqlite3.Connection):
        self._conn = db_connection

    @staticmethod
    def _to_user(row: sqlite3.Row | tuple) -> User:
        return User(
            id=row[0],
            username=row[1],
            email=row[2],
            hashed_password=row[3],
            status=UserStatus(row[4]),
            created_at=datetime.fromisoformat(row[5]),
        )

    def get_by_username(self, username: str) -> User | None:
        with sqlite_errors():
            row = self._conn.execute(
                "SELECT id, username, email, hashed_password, status, created_at "
                "FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return self._to_user(row) if row is not None else None

    def get_by_id(self, user_id: str) -> User | None:
        with sqlite_errors():
            row = self._conn.execute(
                "SELECT id, username, email, hashed_password, status, created_at "
                "FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._to_user(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        with sqlite_errors():
            row = self._conn.execute(
                "SELECT id, username, email, hashed_password, status, created_at "
                "FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        return self._to_user(row) if row is not None else None

    def save(self, user: User) -> None:
        with sqlite_errors():
            self._conn.execute(
                "INSERT INTO users "
                "(id, username, email, hashed_password, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user.id,
                    user.username,
                    user.email,
                    user.hashed_password,
                    user.status.value,
                    user.created_at.isoformat(),
                ),
            )
            self._conn.commit()

    def update(self, user: User) -> None:
        with sqlite_errors():
            cur = self._conn.execute(
                "UPDATE users SET username = ?, email = ?, hashed_password = ?, "
                "status = ?, created_at = ? WHERE id = ?",
                (
                    user.username,
                    user.email,
                    user.hashed_password,
                    user.status.value,
                    user.created_at.isoformat(),
                    user.id,
                ),
            )
            self._conn.commit()
        if cur.rowcount == 0:
            raise RecordNotFound(f"User {user.id!r} not found")

    def delete(self, user_id: str) -> None:
        with sqlite_errors():
            cur = self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self._conn.commit()
        if cur.rowcount == 0:
            raise RecordNotFound(f"User {user_id!r} not found")
