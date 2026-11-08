"""Capture sidecar: tshark -> NDJSON over a Unix or TLS socket.

It is an independent collector running in the broker network namespace. It
writes one JSON line per MQTT frame to the agent's socket; the agent consumes it
through `AsyncSocketServer`, which routes each frame to its broker worker.

Only the fields needed to compute the model features and the alert context are
requested from tshark. Passwords, usernames and payloads are never captured.
Each record carries `tcp_features`: the 12 causal TCP features of model B
(`tcp_window_features`). Frames without a 1883/8883 port are not sent.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import ssl
import subprocess
import sys

from .socket_sender import DEFAULT_ENDPOINT, SocketSender, parse_endpoint
from .tcp_window_features import TcpWindowFeatures
from .tshark_schema import CAPTURE_FIELDS, RECORD_FIELDS

FLOAT_FIELDS = {'frame.time_epoch', 'frame.time_delta', 'frame.len'}
INT_FIELDS = {'tcp.srcport', 'tcp.dstport', 'tcp.stream'}

DEFAULT_QUEUE_SIZE = 50_000
DEFAULT_RETRY_SECONDS = 1.0
DEFAULT_CONNECT_TIMEOUT = 10.0


def build_tls_context(args) -> ssl.SSLContext | None:
    """Build the client TLS context when the endpoint uses TLS."""
    scheme, _ = parse_endpoint(args.endpoint)
    if scheme != 'tls':
        return None
    context = (ssl.create_default_context(cafile=args.tls_ca)
               if args.tls_ca else ssl.create_default_context())
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def build_display_filter(base: str, exclude_topic: str | None) -> str:
    """Add a safe topic exclusion to a tshark display filter."""
    if not exclude_topic:
        return base
    # `!(field == value)` also matches records where the field is absent.
    exclusion = f'!(mqtt.topic == "{exclude_topic}")'
    return f'({base}) && {exclusion}' if base else exclusion


def build_command(args, fields=CAPTURE_FIELDS) -> list[str]:
    """Build the line-buffered tshark fields command for the capture config."""
    cmd = [
        'tshark', '-l', '-n',
        '-i', args.iface,
        '-T', 'fields', '-E', 'occurrence=f', '-E', 'quote=d',
    ]
    display_filter = build_display_filter(args.filter, args.exclude_topic)
    if display_filter:
        cmd += ['-Y', display_filter]
    for field in fields:
        cmd += ['-e', field]
    return cmd


def _coerce(field: str, value: str):
    """Convert a tshark field to its schema type, or return ``None``."""
    if value == '':
        return None
    if field in INT_FIELDS:
        try:
            return int(value)
        except ValueError:
            return None
    if field in FLOAT_FIELDS:
        try:
            return float(value)
        except ValueError:
            return None
    return value


def record_from_fields(values: list[str], fields=CAPTURE_FIELDS) -> dict:
    """Map tab-separated tshark output to the capture-side record."""
    return {field: _coerce(field, value)
            for field, value in zip(fields, values)}


def wire_record(record: dict, features: dict,
                identity: dict | None = None) -> dict:
    """Build the record sent to the agent (no msgtype, only safe fields)."""
    wire = {field: record.get(field) for field in RECORD_FIELDS
            if field != 'tcp_features'}
    if identity:
        wire.update({key: value for key, value in identity.items() if value})
    wire['tcp_features'] = features
    return wire


def apply_enrollment(args, credentials) -> None:
    """Fill identity, agent endpoint and CA from the enrollment state.

    Explicit flags or environment variables keep priority, so a site can
    override the agent address (for example behind a proxy).
    """
    identity = credentials.identity()
    args.tenant_id = identity['tenant_id']
    args.broker_id = identity['broker_id']
    args.sensor_id = identity['sensor_id']
    state = credentials.state
    args.endpoint = args.endpoint or state.agent_endpoint
    args.tls_ca = args.tls_ca or credentials.ca_path
    args.tls_server_name = args.tls_server_name or state.agent_server_name or None


def enroll(args):
    """Return started credentials, or ``None`` when no ENROLL_KEY is set."""
    if not args.enroll_key:
        return None
    if not args.api_url:
        raise SystemExit('ENROLL_KEY requiere API_URL')
    from .enrollment import ApiClient, EnrollmentError, SensorCredentials

    credentials = SensorCredentials(
        ApiClient(args.api_url, ca_file=args.api_ca), args.state_dir,
        args.enroll_key, name=args.sensor_name)
    try:
        credentials.ensure()
    except EnrollmentError as exc:
        print(f'[capture] inscripción rechazada: {exc}', file=sys.stderr,
              flush=True)
        return False
    apply_enrollment(args, credentials)
    credentials.start()
    return credentials


def stream(args) -> int:
    """Run tshark and send each captured record to the agent socket."""
    credentials = enroll(args)
    if credentials is False:
        return 3
    args.endpoint = args.endpoint or DEFAULT_ENDPOINT
    registry = subprocess.run(['tshark', '-G', 'fields'], capture_output=True, text=True)
    if registry.returncode:
        print(registry.stderr, file=sys.stderr)
        return registry.returncode
    available = {line.split('\t')[2] for line in registry.stdout.splitlines()
                 if line.startswith('F\t') and len(line.split('\t')) > 2}
    fields = tuple(field for field in CAPTURE_FIELDS if field in available)
    missing = set(CAPTURE_FIELDS) - available
    if missing:
        print(f'[capture] campos no disponibles, se guardan como null: {sorted(missing)}',
              file=sys.stderr)
    cmd = build_command(args, fields)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=None, text=True, bufsize=1)
    except FileNotFoundError:
        print('tshark no encontrado en PATH', file=sys.stderr)
        return 1

    if args.verbose:
        print(f"[capture] {' '.join(cmd)}", file=sys.stderr)

    sender = SocketSender(args.endpoint, queue_size=args.queue_size,
                          retry_seconds=args.retry_seconds,
                          tls_context=build_tls_context(args),
                          server_name=args.tls_server_name,
                          sensor_token=args.sensor_token,
                          connect_timeout=args.connect_timeout,
                          token_provider=(credentials.token if credentials
                                          and parse_endpoint(args.endpoint)[0] == 'tls'
                                          else None))
    sender.start()
    identity = {'tenant_id': args.tenant_id, 'broker_id': args.broker_id,
                'sensor_id': args.sensor_id}
    try:
        excluded_streams = set()
        tcp_features = TcpWindowFeatures()
        assert proc.stdout is not None
        for line in proc.stdout:
            values = next(csv.reader([line.rstrip('\n')], delimiter='\t'))
            record = record_from_fields(values, fields)
            record.update({field: None for field in missing})
            stream_id = record.get('tcp.stream')
            if (args.exclude_client_id
                    and record.get('mqtt.clientid') == args.exclude_client_id):
                excluded_streams.add(stream_id)
            if stream_id is not None and stream_id in excluded_streams:
                continue
            # Después de las exclusiones: el tráfico del agente no entra a las ventanas.
            features = tcp_features.update(record)
            if features is None:
                continue
            sender.send(json.dumps(wire_record(record, features, identity),
                                   ensure_ascii=False) + '\n')
    except KeyboardInterrupt:
        pass
    finally:
        sender.close()
        if credentials:
            credentials.stop()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if proc.returncode not in (0, -15, None):
        print(f'[capture] tshark salio con {proc.returncode}',
              file=sys.stderr)
        return proc.returncode
    return 0


def parse_args(argv=None):
    """Parse command-line options for the capture sidecar."""
    ap = argparse.ArgumentParser(
        description='Capture with tshark and stream features to the agent socket')
    ap.add_argument('--iface', default='eth0', help='Capture interface')
    ap.add_argument('--filter', default='',
                    help='Display filter opcional; vacío captura todas las tramas')
    ap.add_argument('--exclude-topic', dest='exclude_topic', default=None,
                    help='Topic to exclude (for example, alertas/deteccion)')
    ap.add_argument('--endpoint', '--socket', dest='endpoint',
                    default=os.getenv('CAPTURE_ENDPOINT') or None,
                    help='unix:///ruta o tls://host:puerto del agente '
                         '(por defecto el de la inscripción o el socket local)')
    ap.add_argument('--enroll-key', dest='enroll_key',
                    default=os.getenv('ENROLL_KEY') or None,
                    help='Clave de inscripción del broker (desde la web)')
    ap.add_argument('--api-url', dest='api_url',
                    default=os.getenv('API_URL') or None,
                    help='URL pública de la API, p. ej. https://api.example.com')
    ap.add_argument('--api-ca', dest='api_ca',
                    default=os.getenv('API_CA') or None,
                    help='CA para la API cuando no usa un certificado público')
    ap.add_argument('--state-dir', dest='state_dir',
                    default=os.getenv('STATE_DIR', '/state'),
                    help='Directorio persistente de la identidad del sensor')
    ap.add_argument('--sensor-name', dest='sensor_name',
                    default=os.getenv('SENSOR_NAME') or None,
                    help='Nombre visible del sensor (por defecto el hostname)')
    ap.add_argument('--tls-ca', dest='tls_ca',
                    default=os.getenv('TLS_CA') or None,
                    help='CA para verificar el certificado del agente')
    ap.add_argument('--tls-server-name', dest='tls_server_name',
                    default=os.getenv('TLS_SERVER_NAME') or None,
                    help='Nombre esperado en el certificado del agente')
    ap.add_argument('--sensor-token', dest='sensor_token',
                    default=os.getenv('SENSOR_TOKEN') or None,
                    help='JWT de sensor enviado en el frame hello')
    ap.add_argument('--queue-size', dest='queue_size', type=int,
                    default=DEFAULT_QUEUE_SIZE,
                    help='Máximo de registros en cola antes de descartar')
    ap.add_argument('--retry-seconds', dest='retry_seconds', type=float,
                    default=DEFAULT_RETRY_SECONDS,
                    help='Segundos entre intentos de conexión al agente')
    ap.add_argument('--connect-timeout', dest='connect_timeout', type=float,
                    default=DEFAULT_CONNECT_TIMEOUT,
                    help='Timeout de conexión y TLS en segundos')
    ap.add_argument('--exclude-client-id', default='agente-alertas',
                    help='Excluir el stream del publisher de alertas tras observar su CONNECT')
    ap.add_argument('--tenant-id', default=os.getenv('TENANT_ID', ''),
                    help='Propietario de la infraestructura (tenant_id)')
    ap.add_argument('--broker-id', default=os.getenv('BROKER_ID', ''),
                    help='Identificador del broker MQTT (broker_id)')
    ap.add_argument('--sensor-id', default=os.getenv('SENSOR_ID', ''),
                    help='Identificador de esta instalación de captura (sensor_id)')
    ap.add_argument('--verbose', action='store_true')
    return ap.parse_args(argv)


def main(argv=None) -> int:
    """Validate the environment and run the capture sidecar."""
    args = parse_args(argv)
    if shutil.which('tshark') is None and sys.platform != 'win32':
        print('aviso: tshark no esta en PATH', file=sys.stderr)
    return stream(args)


if __name__ == '__main__':
    sys.exit(main())
