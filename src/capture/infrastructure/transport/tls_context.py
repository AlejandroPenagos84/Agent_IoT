"""Contexto TLS del cliente para conectar con el agente remoto."""

from __future__ import annotations

import ssl

from wire.protocol import TLS, parse_endpoint


def client_tls_context(endpoint: str, ca_file: str | None = None) -> ssl.SSLContext | None:
    """Contexto con verificación estricta si el endpoint es ``tls://``; si no, ``None``."""
    scheme, _ = parse_endpoint(endpoint)
    if scheme != TLS:
        return None
    context = (
        ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
    )
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context
