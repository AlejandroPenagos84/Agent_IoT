from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from auth.application.errors import (ExpiredToken, MalformedToken, TokenMissingFamily,
                                     TokenTypeMismatch)
from auth.application.ports.token_service import AccessClaims, RefreshClaims, TokenData

ALGORITHM = "HS256"
REQUIRED_CLAIMS = ["exp", "iat", "sub", "jti", "type"]


def _from_ts(value: int | float) -> datetime:
    return datetime.fromtimestamp(value, timezone.utc)


class PyJwtTokenService:
    def __init__(self, secret: str, access_ttl: int, refresh_ttl: int):
        """``access_ttl`` y ``refresh_ttl`` en minutos."""
        self._secret = secret
        self._access_ttl = timedelta(minutes=access_ttl)
        self._refresh_ttl = timedelta(minutes=refresh_ttl)

    def create_access(self, user_id: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,                   # usuario dueño del token
            "jti": str(uuid4()),              # identificador único del token
            "type": "access",                 # tipo de token
            "iat": now,                       # cuándo se creó
            "exp": now + self._access_ttl,    # cuándo expira
        }
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def create_refresh(self, user_id: str, family_id: str) -> TokenData:
        now = datetime.now(timezone.utc)
        jti = str(uuid4())
        expires_at = now + self._refresh_ttl
        payload = {
            "sub": user_id,
            "jti": jti,
            "fam": family_id,                 # familia de tokens (rotación)
            "type": "refresh",
            "iat": now,
            "exp": expires_at,
        }
        token = jwt.encode(payload, self._secret, algorithm=ALGORITHM)
        # JWT guarda exp en segundos enteros; se trunca igual aquí.
        return TokenData(token=token, jti=jti, expires_at=expires_at.replace(microsecond=0))

    def decode_access(self, token: str) -> AccessClaims:
        payload = self._decode(token, "access")
        return AccessClaims(sub=payload["sub"], jti=payload["jti"],
                            exp=_from_ts(payload["exp"]))

    def decode_refresh(self, token: str) -> RefreshClaims:
        payload = self._decode(token, "refresh")
        if "fam" not in payload:
            raise TokenMissingFamily("Refresh token without family")
        return RefreshClaims(sub=payload["sub"], jti=payload["jti"],
                             family_id=payload["fam"], exp=_from_ts(payload["exp"]))

    def _decode(self, token: str, expected_type: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],                 # nunca confiar en el header
                options={"require": REQUIRED_CLAIMS},   # exige estos claims
            )
        except jwt.ExpiredSignatureError as exc:
            raise ExpiredToken("Token has expired") from exc
        except jwt.MissingRequiredClaimError as exc:
            raise MalformedToken("Token is missing required claims") from exc
        except jwt.InvalidTokenError as exc:
            raise MalformedToken("Invalid token") from exc
        if payload["type"] != expected_type:
            raise TokenTypeMismatch("Unexpected token type")
        return payload
