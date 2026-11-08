"""SQLite registry for brokers, sensors and alerts."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS brokers (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    name        TEXT NOT NULL,
    host        TEXT,
    port        INTEGER,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_brokers_tenant ON brokers (tenant_id);

CREATE TABLE IF NOT EXISTS sensors (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    broker_id   TEXT NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sensors_tenant ON sensors (tenant_id);
CREATE INDEX IF NOT EXISTS ix_sensors_broker ON sensors (broker_id);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id    TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    broker_id   TEXT,
    sensor_id   TEXT,
    ts          REAL NOT NULL,
    kind        TEXT NOT NULL,
    label       TEXT NOT NULL,
    client_id   TEXT,
    ip          TEXT,
    topic       TEXT,
    mse         REAL,
    source      TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_alerts_tenant_ts ON alerts (tenant_id, ts);
CREATE INDEX IF NOT EXISTS ix_alerts_sensor ON alerts (sensor_id);
"""


# Columns added after the first release. ``CREATE TABLE IF NOT EXISTS`` does not
# alter existing databases, so they are added here when missing.
MIGRATIONS = (
    ('brokers', 'enrollment_key_hash', 'TEXT'),
    ('sensors', 'secret_hash', 'TEXT'),
    ('sensors', 'last_seen', 'TEXT'),
)
MIGRATION_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_brokers_enrollment
    ON brokers (enrollment_key_hash);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sensors_secret ON sensors (secret_hash);
"""


class SensorExistsError(ValueError):
    """Raised when a broker already has its capture sensor."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, kind in MIGRATIONS:
        columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        if column not in columns:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {kind}')
    conn.executescript(MIGRATION_INDEXES)
    conn.commit()


def connect(path: str) -> sqlite3.Connection:
    """Open the registry database, creating parent directories and tables."""
    if path != ':memory:':
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


class RegistryStore:
    """CRUD operations for brokers, sensors and alerts."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self._lock = threading.Lock()

    def create_broker(self, tenant_id: str, name: str,
                      host: str | None = None,
                      port: int | None = None,
                      enrollment_key_hash: str | None = None) -> dict:
        broker = {
            'id': str(uuid4()),
            'tenant_id': tenant_id,
            'name': name,
            'host': host,
            'port': port,
            'enrollment_key_hash': enrollment_key_hash,
            'created_at': _now(),
        }
        with self._lock:
            self.connection.execute(
                'INSERT INTO brokers (id, tenant_id, name, host, port, '
                'enrollment_key_hash, created_at) VALUES (:id, :tenant_id, '
                ':name, :host, :port, :enrollment_key_hash, :created_at)',
                broker)
            self.connection.commit()
        return broker

    def set_enrollment_key(self, tenant_id: str, broker_id: str,
                           key_hash: str) -> bool:
        """Replace the broker key and revoke the current sensor credentials."""
        with self._lock:
            cursor = self.connection.execute(
                'UPDATE brokers SET enrollment_key_hash = ? '
                'WHERE tenant_id = ? AND id = ?', (key_hash, tenant_id, broker_id))
            if cursor.rowcount:
                self.connection.execute(
                    'UPDATE sensors SET secret_hash = NULL WHERE broker_id = ?',
                    (broker_id,))
            self.connection.commit()
        return cursor.rowcount > 0

    def broker_by_enrollment_key(self, key_hash: str) -> dict | None:
        row = self.connection.execute(
            'SELECT * FROM brokers WHERE enrollment_key_hash = ?',
            (key_hash,)).fetchone()
        return dict(row) if row else None

    def enroll_sensor(self, broker: dict, name: str, secret_hash: str) -> dict:
        """Create the broker's sensor or replace its credentials (reinstall)."""
        now = _now()
        with self._lock:
            row = self.connection.execute(
                'SELECT * FROM sensors WHERE broker_id = ? ORDER BY created_at '
                'LIMIT 1', (broker['id'],)).fetchone()
            if row is None:
                sensor = {'id': str(uuid4()), 'tenant_id': broker['tenant_id'],
                          'broker_id': broker['id'], 'name': name,
                          'secret_hash': secret_hash, 'last_seen': now,
                          'created_at': now}
                self.connection.execute(
                    'INSERT INTO sensors (id, tenant_id, broker_id, name, '
                    'secret_hash, last_seen, created_at) VALUES (:id, '
                    ':tenant_id, :broker_id, :name, :secret_hash, :last_seen, '
                    ':created_at)', sensor)
            else:
                sensor = {**dict(row), 'name': name, 'secret_hash': secret_hash,
                          'last_seen': now}
                self.connection.execute(
                    'UPDATE sensors SET name = ?, secret_hash = ?, last_seen = ? '
                    'WHERE id = ?', (name, secret_hash, now, sensor['id']))
            self.connection.commit()
        return sensor

    def sensor_by_secret(self, secret_hash: str) -> dict | None:
        row = self.connection.execute(
            'SELECT * FROM sensors WHERE secret_hash = ?',
            (secret_hash,)).fetchone()
        return dict(row) if row else None

    def touch_sensor(self, sensor_id: str) -> None:
        with self._lock:
            self.connection.execute('UPDATE sensors SET last_seen = ? WHERE id = ?',
                                    (_now(), sensor_id))
            self.connection.commit()

    def broker_sensor(self, broker_id: str) -> dict | None:
        row = self.connection.execute(
            'SELECT * FROM sensors WHERE broker_id = ? ORDER BY created_at LIMIT 1',
            (broker_id,)).fetchone()
        return dict(row) if row else None

    def list_brokers(self, tenant_id: str) -> list[dict]:
        rows = self.connection.execute(
            'SELECT * FROM brokers WHERE tenant_id = ? ORDER BY created_at',
            (tenant_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_broker(self, tenant_id: str, broker_id: str) -> dict | None:
        row = self.connection.execute(
            'SELECT * FROM brokers WHERE tenant_id = ? AND id = ?',
            (tenant_id, broker_id)).fetchone()
        return dict(row) if row else None

    def delete_broker(self, tenant_id: str, broker_id: str) -> bool:
        """Delete one broker owned by ``tenant_id``; sensors cascade."""
        with self._lock:
            cursor = self.connection.execute(
                'DELETE FROM brokers WHERE tenant_id = ? AND id = ?',
                (tenant_id, broker_id))
            self.connection.commit()
        return cursor.rowcount > 0

    def create_sensor(self, tenant_id: str, broker_id: str, name: str) -> dict | None:
        """Create the broker's only sensor; ``None`` when the broker is missing."""
        broker = self.get_broker(tenant_id, broker_id)
        if broker is None:
            return None
        if self.broker_sensor(broker_id) is not None:
            raise SensorExistsError('El broker ya tiene un sensor de captura')
        sensor = {
            'id': str(uuid4()),
            'tenant_id': tenant_id,
            'broker_id': broker_id,
            'name': name,
            'created_at': _now(),
        }
        with self._lock:
            self.connection.execute(
                'INSERT INTO sensors (id, tenant_id, broker_id, name, created_at) '
                'VALUES (:id, :tenant_id, :broker_id, :name, :created_at)',
                sensor)
            self.connection.commit()
        return sensor

    def list_sensors(self, tenant_id: str, broker_id: str) -> list[dict]:
        rows = self.connection.execute(
            'SELECT * FROM sensors WHERE tenant_id = ? AND broker_id = ? '
            'ORDER BY created_at', (tenant_id, broker_id)).fetchall()
        return [dict(row) for row in rows]

    def get_sensor(self, tenant_id: str, sensor_id: str) -> dict | None:
        row = self.connection.execute(
            'SELECT * FROM sensors WHERE tenant_id = ? AND id = ?',
            (tenant_id, sensor_id)).fetchone()
        return dict(row) if row else None

    def add_alert(self, alert: dict) -> bool:
        """Insert an alert; return ``False`` when the ``alert_id`` already exists."""
        record = {
            'alert_id': alert['alert_id'],
            'tenant_id': alert['tenant_id'],
            'broker_id': alert.get('broker_id'),
            'sensor_id': alert.get('sensor_id'),
            'ts': float(alert['ts']),
            'kind': alert['kind'],
            'label': alert['label'],
            'client_id': alert.get('client_id'),
            'ip': alert.get('ip'),
            'topic': alert.get('topic'),
            'mse': alert.get('mse'),
            'source': alert.get('source'),
            'created_at': _now(),
        }
        with self._lock:
            cursor = self.connection.execute(
                'INSERT OR IGNORE INTO alerts (alert_id, tenant_id, broker_id, '
                'sensor_id, ts, kind, label, client_id, ip, topic, mse, source, '
                'created_at) VALUES (:alert_id, :tenant_id, :broker_id, '
                ':sensor_id, :ts, :kind, :label, :client_id, :ip, :topic, '
                ':mse, :source, :created_at)', record)
            self.connection.commit()
        return cursor.rowcount > 0

    def list_alerts(self, tenant_id: str, limit: int | None = 100,
                    broker_id: str | None = None,
                    sensor_id: str | None = None,
                    since: float | None = None,
                    until: float | None = None) -> list[dict]:
        """Return the tenant's alerts, newest first.

        ``since`` is inclusive and ``until`` exclusive (epoch seconds).
        ``limit=None`` returns every matching row.
        """
        query = 'SELECT * FROM alerts WHERE tenant_id = ?'
        params: list = [tenant_id]
        if broker_id is not None:
            query += ' AND broker_id = ?'
            params.append(broker_id)
        if sensor_id is not None:
            query += ' AND sensor_id = ?'
            params.append(sensor_id)
        if since is not None:
            query += ' AND ts >= ?'
            params.append(float(since))
        if until is not None:
            query += ' AND ts < ?'
            params.append(float(until))
        query += ' ORDER BY ts DESC'
        if limit is not None:
            query += ' LIMIT ?'
            params.append(limit)
        rows = self.connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_alert(self, tenant_id: str, alert_id: str) -> dict | None:
        row = self.connection.execute(
            'SELECT * FROM alerts WHERE tenant_id = ? AND alert_id = ?',
            (tenant_id, alert_id)).fetchone()
        return dict(row) if row else None
