from typing import Protocol


class VerificationCodeStore(Protocol):
    def save(self, email: str, code_hash: str, ttl_seconds: int) -> None: ...
    def get(self, email: str) -> str | None: ...

    def delete(self, email: str) -> None:
        """Borra el código y el contador de fallos del correo."""
        ...

    def register_failure(self, email: str) -> int:
        """Suma un intento fallido y devuelve el total actual."""
        ...

    def try_start_cooldown(self, email: str, seconds: int) -> bool:
        """Inicia la espera entre envíos; False si todavía hay una espera activa."""
        ...
