from auth.application.errors import InvalidToken
from auth.application.ports.refresh_store import RefreshTokenStore
from auth.application.ports.token_service import TokenService


class Logout:
    def __init__(self, tokens: TokenService, store: RefreshTokenStore) -> None:
        self._tokens = tokens
        self._store = store

    def execute(self, refresh_token: str) -> None:
        try:
            claims = self._tokens.decode_refresh(refresh_token)
        except InvalidToken:
            return

        self._store.revoke(claims.jti)
