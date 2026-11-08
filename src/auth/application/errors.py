"""Errores del módulo auth. La capa HTTP los traduce a códigos de estado."""

from auth.errors import AuthError

__all__ = [
    "AuthError",
    "ApplicationError",
    "AuthenticationError",
    "InvalidCredentials",
    "AccountNotVerified",
    "AccountDisabled",
    "RegistrationError",
    "UserAlreadyExists",
    "VerificationError",
    "InvalidCode",
    "TooManyRequests",
    "SessionError",
    "RevokedToken",
    "RefreshTokenReused",
    "TokenError",
    "InvalidToken",
    "ExpiredToken",
    "MalformedToken",
    "TokenTypeMismatch",
    "TokenMissingFamily",
]


class ApplicationError(AuthError):
    """Error producido por un caso de uso de auth."""


class AuthenticationError(ApplicationError):
    """Falló la autenticación o el acceso no está permitido."""


class InvalidCredentials(AuthenticationError):
    """Usuario o contraseña incorrectos."""


class AccountNotVerified(AuthenticationError):
    """La cuenta existe pero el correo no se ha verificado."""


class AccountDisabled(AuthenticationError):
    """La cuenta fue bloqueada."""


class RegistrationError(ApplicationError):
    """Error durante el registro de una cuenta."""


class UserAlreadyExists(RegistrationError):
    """El username o el correo ya pertenecen a una cuenta activa."""


class VerificationError(ApplicationError):
    """Error durante la verificación del correo."""


class InvalidCode(VerificationError):
    """Código de verificación incorrecto, expirado o inexistente."""


class TooManyRequests(VerificationError):
    """Se pidió un código nuevo antes de que terminara la espera."""


class SessionError(ApplicationError):
    """Error al gestionar una sesión o sus tokens de refresco."""


class RevokedToken(SessionError):
    """El token de refresco fue revocado."""


class RefreshTokenReused(SessionError):
    """Se reutilizó un token de refresco ya rotado; la familia queda inválida."""


class TokenError(ApplicationError):
    """Error al crear o validar un token."""


class InvalidToken(TokenError):
    """JWT expirado, mal firmado, malformado o de un tipo distinto al esperado."""


class ExpiredToken(InvalidToken):
    """El token ya expiró."""


class MalformedToken(InvalidToken):
    """El token está malformado o su firma no es válida."""


class TokenTypeMismatch(InvalidToken):
    """El token es válido pero de un tipo distinto al esperado."""


class TokenMissingFamily(InvalidToken):
    """Un token de refresco no incluye su familia."""
