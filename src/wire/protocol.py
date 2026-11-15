"""Contrato entre la captura (cliente) y el agente (central).

Lo importan los dos lados; no depende de nada fuera de la biblioteca estándar.
Cambiar algo aquí cambia el protocolo: hay que desplegar captura y agente
juntos, y si cambian las features, reentrenar el modelo.

Transporte: NDJSON (un objeto JSON por línea) sobre un socket Unix o TLS.
En TLS la primera línea es ``hello`` con el token de sensor y el agente
responde ``hello_ack`` antes de aceptar registros.
"""

from __future__ import annotations

import json

# ------------------------------------------------------------- endpoints
UNIX = 'unix'
TLS = 'tls'


def parse_endpoint(endpoint: str) -> tuple[str, object]:
    """Return ``('unix', path)`` or ``('tls', (host, port))``."""
    if '://' not in endpoint:
        return UNIX, endpoint
    scheme, rest = endpoint.split('://', 1)
    if scheme == UNIX:
        return UNIX, rest
    if scheme == TLS:
        host, sep, port = rest.rpartition(':')
        if not sep or not host:
            raise ValueError(f'endpoint TLS inválido: {endpoint}')
        return TLS, (host.strip('[]'), int(port))
    raise ValueError(f'esquema de endpoint no soportado: {scheme}')


# ------------------------------------------------------------- handshake
HELLO = 'hello'
HELLO_ACK = 'hello_ack'


def hello_frame(token: str) -> bytes:
    """First line the capture sends on a TLS connection."""
    return (json.dumps({'type': HELLO, 'token': token}) + '\n').encode('utf-8')


HELLO_ACK_FRAME = (json.dumps({'type': HELLO_ACK}, separators=(',', ':')) + '\n').encode('utf-8')


def message_type(line: bytes) -> tuple[str | None, dict | None]:
    """Decode one control line; ``(None, None)`` when it is not a JSON object."""
    try:
        message = json.loads(line.decode('utf-8', errors='replace'))
    except json.JSONDecodeError:
        return None, None
    if not isinstance(message, dict):
        return None, None
    return message.get('type'), message


# ---------------------------------------------------------------- record
# Identidad del sensor que viaja en cada registro (el agente la valida contra
# el token del hello).
IDENTITY_KEYS = ('tenant_id', 'broker_id', 'sensor_id')

# Campos de cada registro que la captura envía al agente.
RECORD_FIELDS = (
    'frame.time_epoch',
    'frame.time_delta',
    'frame.len',
    'ip.src',
    'ip.dst',
    'tcp.srcport',
    'tcp.dstport',
    'tcp.stream',
    'mqtt.clientid',
    'mqtt.topic',
    'tcp_features',
)

# Contenido de ``tcp_features``: mismo orden que ``feature_columns_tcp`` de
# modelos_agente_tcp/pipeline_config.json. Cambiarlo obliga a reentrenar.
TCP_FEATURE_COLUMNS = (
    'frame.len',
    'fe_log_len',
    'frame.time_delta',
    'fe_is_standard_mqtt_port',
    'fe_is_broker_to_client',
    'tcp_iat',
    'tcp_iat_std_5s',
    'tcp_frames_5s',
    'tcp_bytes_5s',
    'tcp_len_std_5s',
    'tcp_asymmetry_5s',
    'tcp_new_conns_5s',
)
