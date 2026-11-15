"""Fachada pública de auth para los demás módulos del monolito."""

from auth.api.identity import Identity
from auth.application.errors import AuthenticationError, InvalidToken, RevokedToken
from auth.application.use_cases.authenticate import Authenticate

# Credencial rechazada. Los fallos de infraestructura (BD caída) no entran aquí:
# deben propagarse como 5xx, no como 401.
_REJECTED = (InvalidToken, RevokedToken, AuthenticationError)


class NotAuthenticated(Exception):
    """El token no corresponde a un usuario activo (inválido, expirado, deshabilitado...)."""


class AuthApi:
    def __init__(self, authenticate: Authenticate):
        self._authenticate = authenticate

    def authenticate(self, access_token: str) -> Identity:
        try:
            user = self._authenticate.execute(access_token)
        except _REJECTED as exc:
            # Los errores internos de auth no cruzan la frontera del módulo.
            raise NotAuthenticated(str(exc)) from exc
        return Identity(user_id=user.id, username=user.username, email=user.email)
