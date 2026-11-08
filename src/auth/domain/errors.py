"""Errores de reglas de negocio del dominio de auth."""

from auth.errors import AuthError


class DomainError(AuthError):
    """Error producido por una regla del dominio."""


class InvalidEmail(DomainError):
    """El correo no tiene un formato válido."""


class InvalidUsername(DomainError):
    """El nombre de usuario no es válido."""


class InvalidPassword(DomainError):
    """La contraseña no cumple la política mínima."""


class InvalidUserState(DomainError):
    """La operación no es válida para el estado actual del usuario."""


class UserNotPending(InvalidUserState):
    """La cuenta ya no está pendiente de verificación."""


class UserNotActive(InvalidUserState):
    """La cuenta no está activa."""
