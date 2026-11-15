"""TLS del lado del agente: contexto del servidor y recarga del certificado."""

from __future__ import annotations

import os
import ssl
import sys
import threading

from wire.protocol import TLS, parse_endpoint


def server_ssl_context(
    endpoint: str, cert: str | None, key: str | None, ca: str | None = None
) -> ssl.SSLContext | None:
    """Contexto TLS de servidor para ``tls://``; ``None`` para Unix.

    ``ca`` se carga como CA de verificación, pero sin ``verify_mode`` el servidor
    no pide certificado de cliente (no hay mTLS): el sensor se autentica con el
    token del ``hello``.
    """
    if parse_endpoint(endpoint)[0] != TLS:
        return None
    if not (cert and key):
        raise ValueError('El endpoint TLS requiere TLS_CERT y TLS_KEY')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    if ca:
        context.load_verify_locations(cafile=ca)
    return context


class CertificateReloader:
    """Reload the server certificate when the files change (ACME renewals).

    ``SSLContext.load_cert_chain`` on the live context applies to new
    handshakes, so renewed certificates are used without restarting.
    """

    def __init__(self, context: ssl.SSLContext, cert: str, key: str, interval: float = 3600.0):
        self.context, self.cert, self.key = context, cert, key
        self.interval = interval
        self._mtime = self._stamp()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='cert-reload', daemon=True)

    def _stamp(self) -> tuple[float, float]:
        try:
            return os.path.getmtime(self.cert), os.path.getmtime(self.key)
        except OSError:
            return (0.0, 0.0)

    def check(self) -> bool:
        stamp = self._stamp()
        if stamp == self._mtime or stamp == (0.0, 0.0):
            return False
        try:
            self.context.load_cert_chain(self.cert, self.key)
        except (OSError, ssl.SSLError) as exc:
            print(
                f'[agente] no se pudo recargar el certificado: {exc}', file=sys.stderr, flush=True
            )
            return False
        self._mtime = stamp
        print('[agente] certificado TLS recargado', file=sys.stderr, flush=True)
        return True

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.check()

    def close(self) -> None:
        self._stop.set()
