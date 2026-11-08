"""Generación y envío del código de verificación; lo usan register y resend."""

import secrets

from auth.application.errors import TooManyRequests
from auth.application.ports.mail_sender import MailSender
from auth.application.ports.password_hasher import PasswordHasher
from auth.application.ports.verification_code_store import VerificationCodeStore

CODE_TTL_SECONDS = 600        # el código vale 10 minutos
RESEND_COOLDOWN_SECONDS = 60  # espera mínima entre dos envíos al mismo correo
MAX_ATTEMPTS = 5              # intentos fallidos antes de invalidar el código


def new_code() -> str:
    """Código de 6 dígitos con un generador criptográficamente seguro."""
    return f"{secrets.randbelow(1_000_000):06d}"


class SendVerificationCode:
    def __init__(self, codes: VerificationCodeStore, hasher: PasswordHasher,
                 mail: MailSender) -> None:
        self.codes = codes
        self.hasher = hasher
        self.mail = mail

    def execute(self, email: str) -> None:
        if not self.codes.try_start_cooldown(email, RESEND_COOLDOWN_SECONDS):
            raise TooManyRequests("Wait before requesting a new code")
        code = new_code()
        self.codes.delete(email)  # invalida el código anterior y reinicia los fallos
        self.codes.save(email, self.hasher.hash(code), CODE_TTL_SECONDS)
        self.mail.send(
            to=email,
            subject="Tu código de verificación",
            body=f"Tu código de verificación es: {code}\n"
                 f"Vence en {CODE_TTL_SECONDS // 60} minutos.",
        )
