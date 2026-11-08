"""Capture-side enrollment: obtain and renew the sensor credentials.

Standard library only, because the capture image ships without the agent
dependencies. The flow is:

1. First start: ``POST /api/v1/sensors/enroll`` with ``ENROLL_KEY``. The
   identity, the sensor secret and the agent CA are saved under ``/state``, so
   a restart does not create a new installation.
2. Every ``refresh_interval_seconds``: ``POST /api/v1/sensors/token/refresh``
   with the sensor secret. It is the heartbeat and, when the token passed half
   of its lifetime, the new token is used for the next connection.
3. A ``401`` on refresh means the sensor was revoked or reinstalled elsewhere.
   The capture stops sending and does not re-enroll with the same key, which
   would kick out the other installation. A new key re-enrolls.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_FILE = 'sensor.json'
CA_FILE = 'agent-ca.crt'
ENROLL_PATH = '/api/v1/sensors/enroll'
REFRESH_PATH = '/api/v1/sensors/token/refresh'
HTTP_TIMEOUT = 15.0
MAX_BACKOFF = 60.0


class EnrollmentError(RuntimeError):
    """Raised when the key or the sensor secret is rejected by the API."""


@dataclass
class SensorState:
    tenant_id: str
    broker_id: str
    sensor_id: str
    sensor_secret: str
    agent_endpoint: str
    agent_server_name: str
    refresh_interval_seconds: int
    enrollment_key_sha256: str
    access_token: str = ''
    expires_at: float = 0.0
    issued_at: float = 0.0
    revoked: bool = False


def _log(message: str) -> None:
    print(f'[enroll] {message}', file=sys.stderr, flush=True)


def _key_digest(key: str) -> str:
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


class ApiClient:
    """Tiny JSON-over-HTTP(S) client."""

    def __init__(self, base_url: str, ca_file: str | None = None,
                 timeout: float = HTTP_TIMEOUT):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.context = None
        if self.base_url.startswith('https://'):
            self.context = ssl.create_default_context(cafile=ca_file)

    def post(self, path: str, body: dict | None = None,
             token: str | None = None) -> dict:
        """Return the JSON body; raise ``EnrollmentError`` on 401/403/404."""
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        request = urllib.request.Request(
            self.base_url + path, method='POST', headers=headers,
            data=json.dumps(body or {}).encode('utf-8'))
        try:
            with urllib.request.urlopen(request, timeout=self.timeout,
                                        context=self.context) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                detail = exc.read().decode('utf-8', errors='replace')[:200]
                raise EnrollmentError(f'HTTP {exc.code}: {detail}') from exc
            raise


class SensorCredentials:
    """Keep the sensor identity and a valid token for the agent connection."""

    def __init__(self, api: ApiClient, state_dir: str | Path,
                 enrollment_key: str, name: str | None = None,
                 clock=time.time):
        self.api = api
        self.state_dir = Path(state_dir)
        self.enrollment_key = enrollment_key
        self.name = name or socket.gethostname()
        self.clock = clock
        self.state: SensorState | None = None
        self.revoked = threading.Event()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- state -------------------------------------------------------------
    @property
    def state_path(self) -> Path:
        return self.state_dir / STATE_FILE

    @property
    def ca_path(self) -> str | None:
        path = self.state_dir / CA_FILE
        return str(path) if path.is_file() else None

    def _load(self) -> SensorState | None:
        try:
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            return SensorState(**data)
        except (OSError, ValueError, TypeError):
            return None

    def _save(self) -> None:
        assert self.state is not None
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f'.{STATE_FILE}.tmp')
        temporary.write_text(json.dumps(asdict(self.state)), encoding='utf-8')
        os.chmod(temporary, 0o600)
        temporary.replace(self.state_path)

    # ---- API calls ---------------------------------------------------------
    def _enroll(self) -> None:
        body = self.api.post(ENROLL_PATH, {'enrollment_key': self.enrollment_key,
                                           'name': self.name[:128]})
        now = self.clock()
        self.state = SensorState(
            tenant_id=body['tenant_id'], broker_id=body['broker_id'],
            sensor_id=body['sensor_id'], sensor_secret=body['sensor_secret'],
            agent_endpoint=body['agent_endpoint'],
            agent_server_name=body.get('agent_server_name') or '',
            refresh_interval_seconds=int(body.get('refresh_interval_seconds', 60)),
            enrollment_key_sha256=_key_digest(self.enrollment_key),
            access_token=body['access_token'],
            expires_at=now + float(body['expires_in']), issued_at=now)
        ca = body.get('agent_ca')
        self.state_dir.mkdir(parents=True, exist_ok=True)
        ca_file = self.state_dir / CA_FILE
        if ca:
            ca_file.write_text(ca, encoding='utf-8')
        else:
            ca_file.unlink(missing_ok=True)
        self._save()
        _log(f'inscrito: broker={self.state.broker_id} '
             f'sensor={self.state.sensor_id}')

    def refresh(self) -> None:
        """Heartbeat; adopt the new token once the current one is half used."""
        assert self.state is not None
        try:
            body = self.api.post(REFRESH_PATH, token=self.state.sensor_secret)
        except EnrollmentError:
            with self._lock:
                self.state.revoked = True
                self._save()
            self.revoked.set()
            raise
        now = self.clock()
        with self._lock:
            lifetime = self.state.expires_at - self.state.issued_at
            if now >= self.state.issued_at + lifetime / 2 or not self.state.access_token:
                self.state.access_token = body['access_token']
                self.state.issued_at = now
                self.state.expires_at = now + float(body['expires_in'])
                self._save()

    # ---- lifecycle ---------------------------------------------------------
    def ensure(self, retry: bool = True) -> SensorState:
        """Load or create the credentials, retrying network errors.

        Raises ``EnrollmentError`` when the key is invalid, or when this
        installation was revoked and the key did not change.
        """
        delay = 1.0
        while True:
            try:
                return self._ensure_once()
            except EnrollmentError:
                raise
            except (OSError, ValueError, KeyError) as exc:
                if not retry or self._stop.is_set():
                    raise
                _log(f'API no disponible ({exc}); reintento en {delay:.0f}s')
                if self._stop.wait(delay):
                    raise
                delay = min(delay * 2, MAX_BACKOFF)

    def _ensure_once(self) -> SensorState:
        state = self._load()
        digest = _key_digest(self.enrollment_key)
        if state is not None and state.enrollment_key_sha256 == digest:
            if state.revoked:
                raise EnrollmentError(
                    'este sensor fue revocado o reinstalado en otro equipo; '
                    'genera una clave nueva en la web')
            self.state = state
            try:
                self.refresh()
                return self.state
            except EnrollmentError:
                raise EnrollmentError(
                    'el sensor fue revocado o reinstalado en otro equipo; '
                    'genera una clave nueva en la web') from None
        # No state, or the user pasted a command with a new key.
        self._enroll()
        assert self.state is not None
        return self.state

    def token(self) -> str | None:
        with self._lock:
            if self.state is None or self.state.revoked:
                return None
            return self.state.access_token

    def identity(self) -> dict:
        assert self.state is not None
        return {'tenant_id': self.state.tenant_id,
                'broker_id': self.state.broker_id,
                'sensor_id': self.state.sensor_id}

    def start(self) -> None:
        """Run the heartbeat/refresh loop in a daemon thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name='sensor-refresh',
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)

    def _loop(self) -> None:
        assert self.state is not None
        interval = max(self.state.refresh_interval_seconds, 5)
        while not self._stop.wait(interval):
            try:
                self.refresh()
            except EnrollmentError as exc:
                _log(f'sensor revocado, se detiene el envío: {exc}')
                return
            except (OSError, ValueError, KeyError) as exc:
                _log(f'no se pudo renovar el token: {exc}')
