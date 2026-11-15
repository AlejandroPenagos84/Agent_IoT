"""Opciones de línea de comandos (y variables de entorno) del sidecar de captura."""

from __future__ import annotations

import argparse
import os

from capture.infrastructure.transport.socket_sender import DEFAULT_QUEUE_SIZE

DEFAULT_RETRY_SECONDS = 1.0
DEFAULT_CONNECT_TIMEOUT = 10.0


def parse_args(argv=None):
    """Parse command-line options for the capture sidecar."""
    ap = argparse.ArgumentParser(
        description='Capture with tshark and stream features to the agent socket'
    )
    ap.add_argument('--iface', default='eth0', help='Capture interface')
    ap.add_argument(
        '--filter', default='', help='Display filter opcional; vacío captura todas las tramas'
    )
    ap.add_argument(
        '--exclude-topic',
        dest='exclude_topic',
        default=None,
        help='Topic to exclude (for example, alertas/deteccion)',
    )
    ap.add_argument(
        '--endpoint',
        '--socket',
        dest='endpoint',
        default=os.getenv('CAPTURE_ENDPOINT') or None,
        help='unix:///ruta o tls://host:puerto del agente '
        '(por defecto el de la inscripción o el socket local)',
    )
    ap.add_argument(
        '--enroll-key',
        dest='enroll_key',
        default=os.getenv('ENROLL_KEY') or None,
        help='Clave de inscripción del broker (desde la web)',
    )
    ap.add_argument(
        '--api-url',
        dest='api_url',
        default=os.getenv('API_URL') or None,
        help='URL pública de la API, p. ej. https://api.example.com',
    )
    ap.add_argument(
        '--api-ca',
        dest='api_ca',
        default=os.getenv('API_CA') or None,
        help='CA para la API cuando no usa un certificado público',
    )
    ap.add_argument(
        '--state-dir',
        dest='state_dir',
        default=os.getenv('STATE_DIR', '/state'),
        help='Directorio persistente de la identidad del sensor',
    )
    ap.add_argument(
        '--sensor-name',
        dest='sensor_name',
        default=os.getenv('SENSOR_NAME') or None,
        help='Nombre visible del sensor (por defecto el hostname)',
    )
    ap.add_argument(
        '--tls-ca',
        dest='tls_ca',
        default=os.getenv('TLS_CA') or None,
        help='CA para verificar el certificado del agente',
    )
    ap.add_argument(
        '--tls-server-name',
        dest='tls_server_name',
        default=os.getenv('TLS_SERVER_NAME') or None,
        help='Nombre esperado en el certificado del agente',
    )
    ap.add_argument(
        '--sensor-token',
        dest='sensor_token',
        default=os.getenv('SENSOR_TOKEN') or None,
        help='JWT de sensor enviado en el frame hello',
    )
    ap.add_argument(
        '--queue-size',
        dest='queue_size',
        type=int,
        default=DEFAULT_QUEUE_SIZE,
        help='Máximo de registros en cola antes de descartar',
    )
    ap.add_argument(
        '--retry-seconds',
        dest='retry_seconds',
        type=float,
        default=DEFAULT_RETRY_SECONDS,
        help='Segundos entre intentos de conexión al agente',
    )
    ap.add_argument(
        '--connect-timeout',
        dest='connect_timeout',
        type=float,
        default=DEFAULT_CONNECT_TIMEOUT,
        help='Timeout de conexión y TLS en segundos',
    )
    ap.add_argument(
        '--exclude-client-id',
        default='agente-alertas',
        help='Excluir el stream del publisher de alertas tras observar su CONNECT',
    )
    ap.add_argument(
        '--tenant-id',
        default=os.getenv('TENANT_ID', ''),
        help='Propietario de la infraestructura (tenant_id)',
    )
    ap.add_argument(
        '--broker-id',
        default=os.getenv('BROKER_ID', ''),
        help='Identificador del broker MQTT (broker_id)',
    )
    ap.add_argument(
        '--sensor-id',
        default=os.getenv('SENSOR_ID', ''),
        help='Identificador de esta instalación de captura (sensor_id)',
    )
    ap.add_argument('--verbose', action='store_true')
    return ap.parse_args(argv)
