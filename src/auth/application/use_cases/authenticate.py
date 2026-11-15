"""Token de acceso -> usuario activo. Única fuente de la regla de sesión válida."""

from auth.application.errors import AccountDisabled, AccountNotVerified, RevokedToken
from auth.application.ports.token_service import TokenService
from auth.application.ports.user_repository import UserRepository
from auth.domain.user import User, UserStatus


class Authenticate:
    def __init__(self, token_service: TokenService, user_repository: UserRepository):
        self._token_service = token_service
        self._user_repository = user_repository

    def execute(self, access_token: str) -> User:
        # InvalidToken / ExpiredToken / TokenTypeMismatch salen del TokenService.
        claims = self._token_service.decode_access(access_token)
        user = self._user_repository.get_by_id(claims.sub)
        if user is None:
            raise RevokedToken('User no longer exists')
        if user.status is UserStatus.PENDING:
            raise AccountNotVerified('Email not verified')
        if user.status is not UserStatus.ACTIVE:
            raise AccountDisabled('Account disabled')
        return user
