"""Estado del sensor en ``STATE_DIR``: ``sensor.json`` (0600) y la CA del agente."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from capture.application.ports.sensor_state_store import SensorStateStore
from capture.domain.sensor_state import SensorState

STATE_FILE = 'sensor.json'
CA_FILE = 'agent-ca.crt'


class FileSensorStateStore(SensorStateStore):
    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)

    @property
    def state_path(self) -> Path:
        return self.state_dir / STATE_FILE

    @property
    def ca_path(self) -> str | None:
        path = self.state_dir / CA_FILE
        return str(path) if path.is_file() else None

    def load(self) -> SensorState | None:
        try:
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            return SensorState(**data)
        except (OSError, ValueError, TypeError):
            return None

    def save(self, state: SensorState) -> None:
        """Escritura atómica: archivo temporal con 0600 y ``replace``."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f'.{STATE_FILE}.tmp')
        temporary.write_text(json.dumps(asdict(state)), encoding='utf-8')
        os.chmod(temporary, 0o600)
        temporary.replace(self.state_path)

    def save_ca(self, pem: str | None) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        ca_file = self.state_dir / CA_FILE
        if pem:
            ca_file.write_text(pem, encoding='utf-8')
        else:
            ca_file.unlink(missing_ok=True)
