import sqlite3
from datetime import datetime, timezone

from auth.application.ports.refresh_store import StoredRefresh
from auth.infrastructure.errors import sqlite_errors


class RefreshTokenStoreSQLite:
    def __init__(self, db_connection: sqlite3.Connection):
        self._conn = db_connection

    def save(self, jti: str, user_id: str, family_id: str, expires_at: datetime) -> None:
        with sqlite_errors():
            self._conn.execute(
                "INSERT INTO refresh_tokens (jti, user_id, family_id, expires_at) VALUES (?, ?, ?, ?)",
                (jti, user_id, family_id, expires_at.isoformat()),
            )
            self._conn.commit()

    def get(self, jti: str) -> StoredRefresh | None:
        with sqlite_errors():
            row = self._conn.execute(
                "SELECT jti, user_id, family_id, expires_at, revoked_at "
                "FROM refresh_tokens WHERE jti = ?", (jti,)
            ).fetchone()
        if row is None:
            return None
        return StoredRefresh(
            jti=row[0],
            user_id=row[1],
            family_id=row[2],
            expires_at=datetime.fromisoformat(row[3]),
            revoked_at=datetime.fromisoformat(row[4]) if row[4] else None,
        )

    def rotate(self, old_jti: str, new_jti: str) -> bool:
        with sqlite_errors():
            cur = self._conn.execute(
                "UPDATE refresh_tokens SET revoked_at = ?, replaced_by = ? "
                "WHERE jti = ? AND revoked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), new_jti, old_jti),
            )
            self._conn.commit()
        return cur.rowcount == 1

    def revoke(self, jti: str) -> None:
        with sqlite_errors():
            self._conn.execute(
                "UPDATE refresh_tokens SET revoked_at = ? WHERE jti = ? AND revoked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), jti),
            )
            self._conn.commit()

    def revoke_family(self, family_id: str) -> None:
        with sqlite_errors():
            self._conn.execute(
                "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), family_id),
            )
            self._conn.commit()
