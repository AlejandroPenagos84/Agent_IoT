"""Sidecar de captura: tshark -> NDJSON por socket Unix o TLS.

Es un colector independiente que corre en el namespace de red del broker.
Escribe una línea JSON por frame MQTT en el socket del agente, que la consume con
``detection.infrastructure.transport.AsyncSocketServer`` y la enruta al worker
de su broker.

A tshark solo se le piden los campos necesarios para las features del modelo y
el contexto de la alerta: nunca contraseñas, usuarios ni payloads. Cada registro
lleva ``tcp_features``, las 12 features TCP causales del modelo B.

Aquí solo se arma la aplicación: los casos de uso viven en
``capture.application.use_cases`` (``EnrollSensor``, ``RefreshSensorToken``,
``StreamFeatures``) y los adaptadores en ``capture.infrastructure``.
"""

from __future__ import annotations

import shutil
import sys

from capture.application.errors import CaptureStartError, EnrollmentError
from capture.application.use_cases.stream_features import StreamFeatures
from capture.cli import parse_args
from capture.infrastructure.enrollment import ApiClient, SensorCredentials
from capture.infrastructure.transport import DEFAULT_ENDPOINT, SocketSender, client_tls_context
from capture.infrastructure.tshark import TsharkPacketSource
from wire.protocol import TLS, parse_endpoint

EXIT_ENROLLMENT_REJECTED = 3


def apply_enrollment(args, credentials: SensorCredentials) -> None:
    """Completa identidad, endpoint del agente y CA con el estado de la inscripción.

    Los flags o variables de entorno explícitos tienen prioridad, para que un
    sitio pueda cambiar la dirección del agente (por ejemplo, detrás de un proxy).
    """
    identity = credentials.identity()
    args.tenant_id = identity['tenant_id']
    args.broker_id = identity['broker_id']
    args.sensor_id = identity['sensor_id']
    state = credentials.state
    args.endpoint = args.endpoint or state.agent_endpoint
    args.tls_ca = args.tls_ca or credentials.ca_path
    args.tls_server_name = args.tls_server_name or state.agent_server_name or None


def build_credentials(args) -> SensorCredentials | None:
    """Credenciales del sensor, o ``None`` si no hay ``ENROLL_KEY``."""
    if not args.enroll_key:
        return None
    if not args.api_url:
        raise SystemExit('ENROLL_KEY requiere API_URL')
    return SensorCredentials(
        ApiClient(args.api_url, ca_file=args.api_ca),
        args.state_dir,
        args.enroll_key,
        name=args.sensor_name,
    )


def build_sender(args, credentials: SensorCredentials | None) -> SocketSender:
    tls = parse_endpoint(args.endpoint)[0] == TLS
    return SocketSender.from_endpoint(
        args.endpoint,
        queue_size=args.queue_size,
        retry_seconds=args.retry_seconds,
        tls_context=client_tls_context(args.endpoint, args.tls_ca),
        server_name=args.tls_server_name,
        sensor_token=args.sensor_token,
        connect_timeout=args.connect_timeout,
        token_provider=credentials.token if credentials and tls else None,
    )


def build_source(args) -> TsharkPacketSource:
    return TsharkPacketSource(args.iface, args.filter, args.exclude_topic, verbose=args.verbose)


def run(args) -> int:
    """Inscribe el sensor (si hay clave), arranca tshark y transmite las features."""
    credentials = build_credentials(args)
    if credentials is not None:
        try:
            credentials.ensure()
        except EnrollmentError as exc:
            print(f'[capture] inscripción rechazada: {exc}', file=sys.stderr, flush=True)
            return EXIT_ENROLLMENT_REJECTED
        apply_enrollment(args, credentials)
        credentials.start()

    try:
        args.endpoint = args.endpoint or DEFAULT_ENDPOINT
        source = build_source(args)
        try:
            source.open()
        except CaptureStartError as exc:
            print(f'[capture] {exc}', file=sys.stderr, flush=True)
            return exc.exit_code

        stream = StreamFeatures(
            source,
            build_sender(args, credentials),
            identity={
                'tenant_id': args.tenant_id,
                'broker_id': args.broker_id,
                'sensor_id': args.sensor_id,
            },
            exclude_client_id=args.exclude_client_id,
        )
        return stream.execute()
    finally:
        if credentials is not None:
            credentials.stop()


def main(argv=None) -> int:
    """Valida el entorno y corre el sidecar de captura."""
    args = parse_args(argv)
    if shutil.which('tshark') is None and sys.platform != 'win32':
        print('aviso: tshark no esta en PATH', file=sys.stderr)
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
