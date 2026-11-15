"""Apertura del socket hacia el agente, según el esquema del endpoint."""

from __future__ import annotations

import socket
import ssl
from typing import Protocol

from capture.infrastructure.transport.tls_connector import TlsConnector
from capture.infrastructure.transport.unix_connector import UnixConnector
from wire.protocol import TLS, parse_endpoint


class Connector(Protocol):
    """Abre una conexión nueva al agente; lanza ``OSError`` o ``ssl.SSLError`` si falla."""

    def open(self, timeout: float) -> socket.socket: ...


def connector_for(
    endpoint: str,
    tls_context: ssl.SSLContext | None = None,
    server_name: str | None = None,
) -> Connector:
    """Connector para ``unix:///ruta``, una ruta sin esquema o ``tls://host:puerto``."""
    scheme, address = parse_endpoint(endpoint)

    if scheme != TLS:
        return UnixConnector(str(address))

    if tls_context is None:
        raise ValueError(f'endpoint TLS sin contexto SSL: {endpoint}')

    host, port = address
    return TlsConnector(host, port, tls_context, server_name=server_name)
