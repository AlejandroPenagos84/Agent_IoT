# auth/application/ports/token_service.py
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TokenData:
    token: str
    jti: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AccessClaims:
    sub: str            # user_id
    jti: str
    exp: datetime


@dataclass(frozen=True, slots=True)
class RefreshClaims:
    sub: str            # user_id
    jti: str
    family_id: str
    exp: datetime


class TokenService(Protocol):
    def create_access(self, user_id: str) -> str: ...
    def create_refresh(self, user_id: str, family_id: str) -> TokenData: ...
    def decode_access(self, token: str) -> AccessClaims: ...
    def decode_refresh(self, token: str) -> RefreshClaims: ...