"""Lo que la central le dice a una captura nueva: direcciones públicas e instalación."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OnboardingConfig:
    """Direcciones públicas que usa la captura y la plantilla del comando de instalación.

    Son las direcciones vistas desde el sitio del cliente, no en las que escuchan
    los servicios. Los valores por defecto sirven para una ejecución local con
    los certificados de ``deploy/certgen.sh`` (SAN ``app``, ``localhost``,
    ``127.0.0.1``); Compose y producción los cambian por variables de entorno.
    """

    public_api_url: str = 'http://localhost:8000'
    agent_endpoint: str = 'tls://localhost:8443'
    # Debe estar en el SAN del certificado del agente.
    agent_server_name: str = 'localhost'
    agent_ca_path: Path | None = None
    capture_image: str = 'proyecto-capture:latest'
    online_seconds: int = 180
    refresh_seconds: int = 60

    @classmethod
    def from_env(cls) -> OnboardingConfig:
        ca = os.getenv('AGENT_CA_PATH', '/certs/agent/ca.crt')
        return cls(
            public_api_url=os.getenv('PUBLIC_API_URL', cls.public_api_url).rstrip('/'),
            agent_endpoint=os.getenv('AGENT_PUBLIC_ENDPOINT', cls.agent_endpoint),
            agent_server_name=os.getenv('AGENT_TLS_SERVER_NAME', cls.agent_server_name),
            agent_ca_path=Path(ca) if ca else None,
            capture_image=os.getenv('CAPTURE_IMAGE', cls.capture_image),
            online_seconds=int(os.getenv('SENSOR_ONLINE_SECONDS', str(cls.online_seconds))),
            refresh_seconds=int(os.getenv('SENSOR_REFRESH_SECONDS', str(cls.refresh_seconds))),
        )

    def agent_ca(self) -> str | None:
        """PEM de la CA del agente, o ``None`` si el agente usa una CA pública."""
        if self.agent_ca_path is None or not self.agent_ca_path.is_file():
            return None
        return self.agent_ca_path.read_text(encoding='utf-8')

    def install_command(self, enrollment_key: str, mosquitto_container: str = 'mosquitto') -> str:
        """Comando que el usuario pega en el host del broker para instalar la captura."""
        return ' \\\n  '.join(
            [
                'docker run -d --name agentiot-capture --restart unless-stopped',
                f'--network container:{mosquitto_container} --cap-add NET_RAW',
                '-v agentiot-capture-state:/state',
                f'-e ENROLL_KEY={shlex.quote(enrollment_key)}',
                f'-e API_URL={shlex.quote(self.public_api_url)}',
                shlex.quote(self.capture_image),
            ]
        )
