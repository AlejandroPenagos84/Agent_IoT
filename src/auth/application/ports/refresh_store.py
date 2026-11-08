# auth/application/ports/refresh_store.py
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredRefresh:
    jti: str
    user_id: str
    family_id: str
    expires_at: datetime
    revoked_at: datetime | None   # None = sigue válido
    
class RefreshTokenStore(Protocol):
    def save(self, jti: str, user_id: str, family_id: str, expires_at: datetime) -> None: ...
    def get(self, jti: str) -> StoredRefresh | None: ...
    def rotate(self, old_jti: str, new_jti: str) -> bool: ...   # atómico; False si ya estaba revocado
    def revoke(self, jti: str) -> None: ...
    def revoke_family(self, family_id: str) -> None: ...