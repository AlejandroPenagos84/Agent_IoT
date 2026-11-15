"""Register the local Mosquitto broker for development.

Laboratory helper, run inside the ``app`` container. It does the same thing a
user does in the web ("Agregar broker") and prints the enrollment key for the
lab capture, which then enrolls itself exactly like a customer installation::

    ENROLL_KEY=$(docker compose exec -T app \
        python -m detection.infrastructure.dev_bootstrap --print-key)

Idempotent: the broker is looked up by name. The plain key is kept in the
bootstrap volume (development only) and reused while it still matches; if it
is missing, a new key is issued, which also revokes the previous capture.

Without ``AUTH_JWT_SECRET`` the key is left empty and the capture runs
without enrollment.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

from detection.infrastructure.enrollment_secrets import ENROLLMENT_PREFIX, hash_secret, new_secret
from detection.infrastructure.repositories.registry_sqlite import (
    RegistryStore,
    connect,
)

DEFAULT_TENANT = 'dev'


def ensure_dev_broker(
    store: RegistryStore, tenant_id: str, name: str, host: str, port: int, known_key: str | None
) -> tuple[dict, str]:
    """Return the dev broker and a valid enrollment key for it."""
    broker = next((item for item in store.list_brokers(tenant_id) if item['name'] == name), None)
    if broker is None:
        key = new_secret(ENROLLMENT_PREFIX)
        broker = store.create_broker(
            tenant_id, name, host, port, enrollment_key_hash=hash_secret(key)
        )
        return broker, key
    if known_key and broker.get('enrollment_key_hash') == hash_secret(known_key):
        return broker, known_key
    key = new_secret(ENROLLMENT_PREFIX)
    store.set_enrollment_key(tenant_id, broker['id'], hash_secret(key))
    return broker, key


def write_env(path: Path, env: dict[str, str]) -> None:
    """Write ``export KEY=value`` lines atomically, readable only by the owner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.tmp')
    temporary.write_text(
        ''.join(f'export {key}={shlex.quote(value)}\n' for key, value in env.items()),
        encoding='utf-8',
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _read_key(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8').strip() or None
    except OSError:
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--db', default=os.getenv('DETECTION_DB_PATH', '/data/detection.db'))
    parser.add_argument('--output', default='/data/dev/dev.env')
    parser.add_argument('--tenant-id', default=os.getenv('DEV_TENANT_ID') or '')
    parser.add_argument('--broker-name', default=os.getenv('DEV_BROKER_NAME', 'mosquitto-dev'))
    parser.add_argument('--broker-host', default='mosquitto')
    parser.add_argument('--broker-port', type=int, default=1883)
    parser.add_argument('--api-url', default=os.getenv('DEV_API_URL') or 'http://app:8000')
    parser.add_argument(
        '--print-key', action='store_true', help='Solo imprime la clave en stdout (laboratorio)'
    )
    args = parser.parse_args(argv)

    tenant_id = args.tenant_id.strip()
    if not tenant_id:
        tenant_id = DEFAULT_TENANT
        print(
            '[bootstrap] DEV_TENANT_ID vacío: el broker queda en el tenant '
            f'"{DEFAULT_TENANT}". Pon tu user id (GET /me) en .env para '
            'verlo con tu token.',
            file=sys.stderr,
        )
    output = Path(args.output)
    key_file = output.with_name('enroll.key')

    connection = connect(args.db)
    try:
        broker, key = ensure_dev_broker(
            RegistryStore(connection),
            tenant_id,
            args.broker_name,
            args.broker_host,
            args.broker_port,
            _read_key(key_file),
        )
    finally:
        connection.close()

    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key + '\n', encoding='utf-8')
    os.chmod(key_file, 0o600)
    if args.print_key:
        # Solo la clave en stdout: ENROLL_KEY=$(... --print-key)
        print(f'[bootstrap] tenant={tenant_id} broker={broker["id"]}', file=sys.stderr)
        print(key)
        return 0
    env = {'ENROLL_KEY': key, 'API_URL': args.api_url}
    if not os.getenv('AUTH_JWT_SECRET'):
        print('[bootstrap] AUTH_JWT_SECRET vacío: la captura no se inscribe.', file=sys.stderr)
        env = {'ENROLL_KEY': '', 'API_URL': ''}
    write_env(output, env)
    print(
        f'[bootstrap] tenant={tenant_id} broker={broker["id"]} ({broker["name"]}) -> {args.output}'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
