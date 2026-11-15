"""Transporte de la captura hacia el agente: socket Unix o TLS con token."""

from capture.infrastructure.transport.socket_sender import (
    DEFAULT_ENDPOINT,
    DEFAULT_QUEUE_SIZE,
    SocketSender,
)
from capture.infrastructure.transport.tls_context import client_tls_context

__all__ = ['DEFAULT_ENDPOINT', 'DEFAULT_QUEUE_SIZE', 'SocketSender', 'client_tls_context']
