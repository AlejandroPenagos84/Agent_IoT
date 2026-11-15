"""MailSender de desarrollo: escribe el correo en el log en vez de enviarlo.

Se usa solo cuando no hay ``AUTH_SMTP_HOST``. El cuerpo incluye el código de
verificación, así que no debe usarse en producción.
"""

import sys


class MailSenderConsole:
    def send(self, to: str, subject: str, body: str) -> None:
        print(f'[mail] to={to} subject={subject!r}\n{body}', file=sys.stderr, flush=True)
