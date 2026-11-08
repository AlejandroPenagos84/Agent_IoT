"""Enrollment keys, sensor secrets and the install command shown to the user."""

from __future__ import annotations

import hashlib
import os
import secrets
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ENROLLMENT_PREFIX = 'ek_'
SENSOR_SECRET_PREFIX = 'ss_'


def new_secret(prefix: str) -> str:
    """Return a random 256-bit secret with a recognizable prefix."""
    return prefix + secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    """SHA-256 of a high-entropy secret. Only the hash is stored."""
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class OnboardingConfig:
    """Public addresses the capture uses and the install command template."""

    public_api_url: str = 'http://localhost:8000'
    agent_endpoint: str = 'tls://localhost:8443'
    agent_server_name: str = 'agente'
    agent_ca_path: Path | None = None
    capture_image: str = 'proyecto-capture:latest'
    online_seconds: int = 180
    refresh_seconds: int = 60

    @classmethod
    def from_env(cls) -> 'OnboardingConfig':
        ca = os.getenv('AGENT_CA_PATH', '/certs/agent/ca.crt')
        return cls(
            public_api_url=os.getenv('PUBLIC_API_URL', cls.public_api_url).rstrip('/'),
            agent_endpoint=os.getenv('AGENT_PUBLIC_ENDPOINT', cls.agent_endpoint),
            agent_server_name=os.getenv('AGENT_TLS_SERVER_NAME',
                                        cls.agent_server_name),
            agent_ca_path=Path(ca) if ca else None,
            capture_image=os.getenv('CAPTURE_IMAGE', cls.capture_image),
            online_seconds=int(os.getenv('SENSOR_ONLINE_SECONDS',
                                         str(cls.online_seconds))),
            refresh_seconds=int(os.getenv('SENSOR_REFRESH_SECONDS',
                                          str(cls.refresh_seconds))),
        )

    def agent_ca(self) -> str | None:
        """PEM of the agent CA, or ``None`` when the agent uses a public CA."""
        if self.agent_ca_path is None or not self.agent_ca_path.is_file():
            return None
        return self.agent_ca_path.read_text(encoding='utf-8')

    def install_command(self, enrollment_key: str,
                        mosquitto_container: str = 'mosquitto') -> str:
        """Command the user pastes on the broker host to install the capture."""
        return ' \\\n  '.join([
            'docker run -d --name agentiot-capture --restart unless-stopped',
            f'--network container:{mosquitto_container} --cap-add NET_RAW',
            '-v agentiot-capture-state:/state',
            f'-e ENROLL_KEY={shlex.quote(enrollment_key)}',
            f'-e API_URL={shlex.quote(self.public_api_url)}',
            shlex.quote(self.capture_image),
        ])


def sensor_status(sensor: dict | None, online_seconds: int,
                  now: datetime | None = None) -> str:
    """``pending`` without sensor, ``connected`` if seen recently, else ``offline``."""
    if sensor is None or not sensor.get('last_seen'):
        return 'pending'
    if not sensor.get('secret_hash'):
        return 'offline'
    seen = datetime.fromisoformat(sensor['last_seen'])
    age = ((now or datetime.now(timezone.utc)) - seen).total_seconds()
    return 'connected' if age <= online_seconds else 'offline'
