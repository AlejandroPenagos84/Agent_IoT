"""Adaptador del puerto IdentityProvider sobre la fachada pública de auth."""

from auth.api import AuthApi, NotAuthenticated
from detection.application.ports.identity_provider import IdentityProvider, UnauthenticatedError


class AuthProvider(IdentityProvider):
    def __init__(self, auth_api: AuthApi):
        self._auth_api = auth_api

    def get_identity(self, access_token: str) -> str:
        try:
            return self._auth_api.authenticate(access_token).user_id
        except NotAuthenticated as exc:
            raise UnauthenticatedError(str(exc)) from exc
