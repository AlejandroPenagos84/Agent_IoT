"""IdentityProvider de pruebas: valida el JWT sin exigir un usuario en auth.

Permite probar la API de detection aislada. La integración real con auth
(usuario activo, deshabilitado...) se prueba en test_app_identity.py.
"""

from auth.application.errors import InvalidToken
from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
from detection.application.ports.identity_provider import IdentityProvider, UnauthenticatedError


class JwtOnlyIdentity(IdentityProvider):
    def __init__(self, secret: str):
        self._tokens = PyJwtTokenService(secret, 15, 10080)

    def get_identity(self, access_token: str) -> str:
        try:
            return self._tokens.decode_access(access_token).sub
        except InvalidToken as exc:
            raise UnauthenticatedError(str(exc)) from exc
