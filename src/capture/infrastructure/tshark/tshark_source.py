"""``PacketSource`` que lee frames de un proceso tshark."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator

from capture.application.errors import CaptureStartError
from capture.application.ports.packet_source import PacketSource
from capture.infrastructure.tshark.command import build_command
from capture.infrastructure.tshark.parser import parse_line
from capture.infrastructure.tshark.schema import CAPTURE_FIELDS

TERMINATE_TIMEOUT = 5.0
# 0: terminó solo; -15: SIGTERM nuestro al cerrar.
CLEAN_EXIT = (0, -15, None)


def _log(message: str) -> None:
    print(f'[capture] {message}', file=sys.stderr, flush=True)


class TsharkPacketSource(PacketSource):
    """Lanza tshark con solo los campos que existen en su versión.

    Los campos de ``CAPTURE_FIELDS`` que tshark no conoce se piden igual en el
    registro, como ``null``, para que el contrato no cambie.
    """

    def __init__(
        self,
        iface: str,
        display_filter: str = '',
        exclude_topic: str | None = None,
        *,
        verbose: bool = False,
    ):
        self._iface = iface
        self._display_filter = display_filter
        self._exclude_topic = exclude_topic
        self._verbose = verbose
        self._fields: tuple[str, ...] = CAPTURE_FIELDS
        self._missing: frozenset[str] = frozenset()
        self._proc: subprocess.Popen | None = None

    def open(self) -> None:
        self._fields, self._missing = self._probe_fields()
        if self._missing:
            _log(f'campos no disponibles, se guardan como null: {sorted(self._missing)}')
        cmd = build_command(self._iface, self._display_filter, self._exclude_topic, self._fields)
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=None, text=True, bufsize=1
            )
        except FileNotFoundError:
            raise CaptureStartError('tshark no encontrado en PATH', exit_code=1) from None
        if self._verbose:
            _log(' '.join(cmd))

    def records(self) -> Iterator[dict]:
        assert self._proc is not None and self._proc.stdout is not None, 'open() primero'
        nulls = dict.fromkeys(self._missing)
        for line in self._proc.stdout:
            record = parse_line(line, self._fields)
            record.update(nulls)
            yield record

    def close(self) -> int:
        proc = self._proc
        if proc is None:
            return 0
        proc.terminate()
        try:
            proc.wait(timeout=TERMINATE_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
        if proc.returncode not in CLEAN_EXIT:
            _log(f'tshark salió con {proc.returncode}')
            return proc.returncode
        return 0

    @staticmethod
    def _probe_fields() -> tuple[tuple[str, ...], frozenset[str]]:
        """Campos de ``CAPTURE_FIELDS`` disponibles y faltantes según ``tshark -G fields``."""
        try:
            registry = subprocess.run(['tshark', '-G', 'fields'], capture_output=True, text=True)
        except FileNotFoundError:
            raise CaptureStartError('tshark no encontrado en PATH', exit_code=1) from None
        if registry.returncode:
            print(registry.stderr, file=sys.stderr)
            raise CaptureStartError('tshark -G fields falló', exit_code=registry.returncode)
        available = {
            parts[2]
            for line in registry.stdout.splitlines()
            if line.startswith('F\t') and len(parts := line.split('\t')) > 2
        }
        fields = tuple(field for field in CAPTURE_FIELDS if field in available)
        return fields, frozenset(CAPTURE_FIELDS) - available
