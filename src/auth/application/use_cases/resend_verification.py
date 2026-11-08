from auth.application.ports.user_repository import UserRepository
from auth.application.use_cases.send_verification_code import SendVerificationCode
from auth.domain.user import UserStatus


class ResendVerification:
    """Reenvía el código solo a cuentas PENDING.

    Si el correo no existe o ya está verificado no hace nada, para que la
    respuesta HTTP sea la misma en todos los casos. Si el correo está en espera
    propaga TooManyRequests.
    """

    def __init__(self, users: UserRepository, send_code: SendVerificationCode) -> None:
        self.users = users
        self.send_code = send_code

    def execute(self, email: str) -> None:
        user = self.users.get_by_email(email)
        if user is not None and user.status is UserStatus.PENDING:
            self.send_code.execute(email)
