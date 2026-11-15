"""Puerto: quién es el dueño (tenant) de un token de acceso de usuario."""

from abc import ABC, abstractmethod


class UnauthenticatedError(Exception):
    pass


class IdentityProvider(ABC):
    @abstractmethod
    def get_identity(self, access_token: str) -> str:
        """Devuelve el tenant_id; lanza ``UnauthenticatedError`` si no es válido."""
