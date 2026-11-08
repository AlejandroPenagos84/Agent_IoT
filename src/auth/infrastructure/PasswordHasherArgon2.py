from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordHasherArgon2:
    def __init__(self, argon2_hasher: Argon2Hasher | None = None) -> None:
        self.argon2_hasher = argon2_hasher or Argon2Hasher()

    def hash(self, plain: str) -> str:
        return self.argon2_hasher.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:  # entregada vs guardada
        try:
            return self.argon2_hasher.verify(hashed, plain)  # ojo: primero el hash, luego la clave
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
