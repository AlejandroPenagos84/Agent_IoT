"""Capture sidecar: tshark -> features.jsonl.

It is an independent collector running in the broker network namespace. It
writes one JSON line per MQTT frame; the agent consumes it through
`TsharkFeatureSource`.

It emits the network fields required by `TsharkFeatureSource` plus frame context
(`frame.time_epoch`, `ip.src`, `mqtt.topic`, and ports).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from .tshark_schema import CAPTURE_FIELDS

# Must match tshark_schema.FEATURE_COLUMNS plus source context fields.
FIELDS = CAPTURE_FIELDS

FLOAT_FIELDS = {
    'frame.time_epoch', 'frame.time_delta', 'frame.time_delta_displayed',
    'frame.time_relative', 'frame.len', 'frame.cap_len',
}
INT_FIELDS = {'tcp.srcport', 'tcp.dstport', 'tcp.stream'}

DEFAULT_OUT = '/capture/features.jsonl'


def build_display_filter(base: str, exclude_topic: str | None) -> str:
    """Add a safe topic exclusion to a tshark display filter."""
    if not exclude_topic:
        return base
    # `!(field == value)` also matches records where the field is absent.
    exclusion = f'!(mqtt.topic == "{exclude_topic}")'
    return f'({base}) && {exclusion}' if base else exclusion


def build_command(args, fields=FIELDS) -> list[str]:
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
    if field == 'mqtt.msg':
        # tshark FT_BYTES -> texto como el CSV de MQTT_UAD.
        try:
            return bytes.fromhex(value.replace(':', '')).decode('utf-8', errors='replace')
        except ValueError:
            return value
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


def record_from_fields(values: list[str], fields=FIELDS) -> dict:
    """Map tab-separated tshark output to a JSON-serializable record."""
    return {field: _coerce(field, value)
            for field, value in zip(fields, values)}


def stream(args) -> int:
    """Run tshark and append each captured record to the JSONL output."""
    registry = subprocess.run(['tshark', '-G', 'fields'], capture_output=True, text=True)
    if registry.returncode:
        print(registry.stderr, file=sys.stderr)
        return registry.returncode
    available = {line.split('\t')[2] for line in registry.stdout.splitlines()
                 if line.startswith('F\t') and len(line.split('\t')) > 2}
    fields = tuple(field for field in FIELDS if field in available)
    missing = set(FIELDS) - available
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

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    if args.verbose:
        print(f"[capture] {' '.join(cmd)}", file=sys.stderr)

    try:
        excluded_streams = set()
        with open(args.out, 'a', encoding='utf-8') as out:
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
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
                out.flush()
    except KeyboardInterrupt:
        pass
    finally:
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
        description='Capture with tshark and write features.jsonl for the agent')
    ap.add_argument('--iface', default='eth0', help='Capture interface')
    ap.add_argument('--filter', default='',
                    help='Display filter opcional; vacío captura todas las tramas')
    ap.add_argument('--exclude-topic', dest='exclude_topic', default=None,
                    help='Topic to exclude (for example, alertas/deteccion)')
    ap.add_argument('--out', default=DEFAULT_OUT,
                    help='Output JSONL file (records are appended)')
    ap.add_argument('--exclude-client-id', default='agente-alertas',
                    help='Excluir el stream del publisher de alertas tras observar su CONNECT')
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
