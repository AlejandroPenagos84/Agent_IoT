from dataclasses import replace

from auth.application.errors import InvalidCode
from auth.application.ports.password_hasher import PasswordHasher
from auth.application.ports.user_repository import UserRepository
from auth.application.ports.verification_code_store import VerificationCodeStore
from auth.application.use_cases.send_verification_code import MAX_ATTEMPTS
from auth.domain.user import User, UserStatus


class VerifyEmail:
    """Valida el código y pasa la cuenta de PENDING a ACTIVE."""

    def __init__(self, users: UserRepository, codes: VerificationCodeStore,
                 hasher: PasswordHasher) -> None:
        self.users = users
        self.codes = codes
        self.hasher = hasher

    def execute(self, email: str, code: str) -> User:
        user = self.users.get_by_email(email)
        stored = self.codes.get(email)
        # Mismo mensaje en todos los casos para no revelar si el correo existe.
        if user is None or user.status is not UserStatus.PENDING or stored is None:
            raise InvalidCode("Code is invalid or expired")

        if not self.hasher.verify(code, stored):
            if self.codes.register_failure(email) >= MAX_ATTEMPTS:
                self.codes.delete(email)  # obliga a pedir un código nuevo
            raise InvalidCode("Code is invalid or expired")

        self.codes.delete(email)
        active = replace(user, status=UserStatus.ACTIVE)
        self.users.update(active)
        return active
