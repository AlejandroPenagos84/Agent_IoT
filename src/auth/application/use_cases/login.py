from uuid import uuid4

from auth.application.dtos import TokenPair
from auth.application.errors import AccountDisabled, AccountNotVerified, InvalidCredentials
from auth.application.ports.password_hasher import PasswordHasher
from auth.application.ports.refresh_store import RefreshTokenStore
from auth.application.ports.token_service import TokenService
from auth.application.ports.user_repository import UserRepository
from auth.domain.user import UserStatus


class LoginUseCase:
    def __init__(self, users: UserRepository, hasher: PasswordHasher,
                 tokens: TokenService, store: RefreshTokenStore) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._store = store

    def execute(self, email: str, password: str) -> TokenPair:
        user = self._users.get_by_email(email)
        if user is None or not self._hasher.verify(password, user.hashed_password):
            raise InvalidCredentials("Invalid email or password")

        if user.status is UserStatus.PENDING:
            raise AccountNotVerified("Email not verified")
        if user.status is not UserStatus.ACTIVE:
            raise AccountDisabled("Account disabled")

        access_token = self._tokens.create_access(user.id)
        family_id = str(uuid4())
        refresh_token = self._tokens.create_refresh(user.id, family_id=family_id)
        self._store.save(
            refresh_token.jti,
            user.id,
            family_id,
            refresh_token.expires_at,
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token.token)
