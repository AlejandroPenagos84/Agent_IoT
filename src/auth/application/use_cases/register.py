from auth.application.dtos import RegisterResult
from auth.application.errors import UserAlreadyExists
from auth.application.ports.password_hasher import PasswordHasher
from auth.application.ports.user_repository import UserRepository
from auth.application.use_cases.send_verification_code import SendVerificationCode
from auth.domain.user import User, UserStatus


class RegisterUser:
    """Crea la cuenta en PENDING y envía el código de verificación."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher,
                 send_code: SendVerificationCode) -> None:
        self.users = users
        self.hasher = hasher
        self.send_code = send_code

    def execute(self, username: str, email: str, password: str) -> RegisterResult:
        by_email = self.users.get_by_email(email)
        by_username = self.users.get_by_username(username)

        if by_email is not None and by_email.status is not UserStatus.PENDING:
            raise UserAlreadyExists("Username or email already in use")
        if by_username is not None and (by_email is None or by_username.id != by_email.id):
            raise UserAlreadyExists("Username or email already in use")

        hashed_password = self.hasher.hash(password)
        if by_email is not None:
            # Registro repetido de una cuenta sin verificar: se actualizan los datos
            # y se envía un código nuevo en lugar de rechazarlo.
            user = User(id=by_email.id, username=username, email=email,
                        hashed_password=hashed_password, status=UserStatus.PENDING,
                        created_at=by_email.created_at)
            self.users.update(user)
        else:
            user = User(id=User.new_id(), username=username, email=email,
                        hashed_password=hashed_password, status=UserStatus.PENDING)
            self.users.save(user)

        # Si el correo falla, la cuenta queda PENDING y se puede usar "reenviar".
        self.send_code.execute(email)
        return RegisterResult.from_user(user)
