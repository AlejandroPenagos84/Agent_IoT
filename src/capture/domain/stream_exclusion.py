"""Exclusión del tráfico propio del agente (su publisher de alertas)."""

from __future__ import annotations


class ClientStreamExclusion:
    """Al ver el CONNECT de ``client_id``, descarta todo su stream TCP.

    Los frames del stream anteriores al CONNECT no se pueden excluir: todavía no
    se sabe a quién pertenecen.
    """

    def __init__(self, client_id: str | None):
        self._client_id = client_id
        self._streams: set = set()

    def excluded(self, record: dict) -> bool:
        stream_id = record.get('tcp.stream')
        if self._client_id and record.get('mqtt.clientid') == self._client_id:
            self._streams.add(stream_id)
        return stream_id is not None and stream_id in self._streams
