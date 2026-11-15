"""Capturar frames, calcular las features TCP y enviarlas al agente."""

from __future__ import annotations

import json

from capture.application.ports.packet_source import PacketSource
from capture.application.ports.record_sender import RecordSender
from capture.domain.stream_exclusion import ClientStreamExclusion
from capture.domain.tcp_window_features import TcpWindowFeatures
from capture.domain.wire_record import wire_record


class StreamFeatures:
    """Bucle principal de la captura.

    Por cada registro: descarta el stream del publisher de alertas, actualiza las
    ventanas TCP y, si el frame produce features, lo envía como una línea NDJSON.
    La exclusión va antes de las ventanas: el tráfico del agente no las contamina.
    """

    def __init__(
        self,
        source: PacketSource,
        sender: RecordSender,
        *,
        identity: dict | None = None,
        exclude_client_id: str | None = None,
        features: TcpWindowFeatures | None = None,
    ):
        self._source = source
        self._sender = sender
        self._identity = identity
        self._exclusion = ClientStreamExclusion(exclude_client_id)
        self._features = features or TcpWindowFeatures()

    def execute(self) -> int:
        """Corre hasta que la fuente termina o llega Ctrl+C; devuelve su código de salida.

        La fuente ya debe estar abierta (``PacketSource.open``).
        """
        self._sender.start()
        try:
            for record in self._source.records():
                self._process(record)
        except KeyboardInterrupt:
            pass
        finally:
            self._sender.close()
            returncode = self._source.close()
        return returncode

    def _process(self, record: dict) -> None:
        if self._exclusion.excluded(record):
            return
        features = self._features.update(record)
        if features is None:
            return
        line = json.dumps(wire_record(record, features, self._identity), ensure_ascii=False)
        self._sender.send(line + '\n')
