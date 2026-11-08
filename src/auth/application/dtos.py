"""DTOs de salida compartidos por los casos de uso de auth."""

from dataclasses import dataclass
from datetime import datetime

from auth.domain.user import User, UserStatus


@dataclass(frozen=True, slots=True)
class RegisterResult:
    id: str
    username: str
    email: str
    status: UserStatus
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "RegisterResult":
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            status=user.status,
            created_at=user.created_at,
        )


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
