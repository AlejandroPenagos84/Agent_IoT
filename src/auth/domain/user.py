from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class UserStatus(str, Enum):
    PENDING = "pending"     # registrado, sin verificar el correo
    ACTIVE = "active"       # verificado, puede iniciar sesión
    DISABLED = "disabled"   # bloqueado por un admin


@dataclass(frozen=True, slots=True)
class User:
    id: str
    username: str
    email: str
    hashed_password: str
    status: UserStatus = UserStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def can_login(self) -> bool:
        return self.status is UserStatus.ACTIVE

    @staticmethod
    def new_id() -> str:
        return str(uuid4())
