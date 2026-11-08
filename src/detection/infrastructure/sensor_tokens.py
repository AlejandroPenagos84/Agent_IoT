"""JWT helpers for user access tokens, sensor tokens and agent tokens."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

ALGORITHM = 'HS256'
ACCESS_CLAIMS = ('exp', 'iat', 'sub', 'jti', 'type')
SENSOR_CLAIMS = ACCESS_CLAIMS + ('tenant_id', 'broker_id', 'sensor_id')
ALERT_TOKEN_TYPES = ('sensor', 'agent')


class TokenError(ValueError):
    """Raised when a JWT is missing, expired, malformed or of the wrong type."""


def _decode(token: str, secret: str, required: tuple[str, ...],
            expected_type: str | None = None) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM],
                             options={'require': list(required)})
    except jwt.ExpiredSignatureError as exc:
        raise TokenError('token ha expirado') from exc
    except jwt.MissingRequiredClaimError as exc:
        raise TokenError('token incompleto') from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError('token inválido') from exc
    if expected_type is not None and payload.get('type') != expected_type:
        raise TokenError('tipo de token incorrecto')
    return payload


def decode_access(token: str, secret: str) -> dict:
    """Validate a user access token issued by the auth service."""
    return _decode(token, secret, ACCESS_CLAIMS, 'access')


def decode_alert_token(token: str, secret: str) -> dict:
    """Validate a sensor or agent token used to ingest alerts."""
    payload = _decode(token, secret, ACCESS_CLAIMS)
    token_type = payload.get('type')
    if token_type not in ALERT_TOKEN_TYPES:
        raise TokenError('tipo de token incorrecto')
    if token_type == 'sensor':
        missing = [key for key in SENSOR_CLAIMS[len(ACCESS_CLAIMS):]
                   if key not in payload]
        if missing:
            raise TokenError(f'token incompleto: {missing}')
    return payload


class SensorTokenService:
    """Issue and validate long-lived tokens that identify one capture sensor."""

    def __init__(self, secret: str, ttl_minutes: int = 10080):
        self.secret = secret
        self.ttl_minutes = ttl_minutes

    def create(self, tenant_id: str, broker_id: str, sensor_id: str) -> tuple[str, int]:
        now = datetime.now(timezone.utc)
        expires_in = self.ttl_minutes * 60
        payload = {
            'sub': sensor_id,
            'jti': str(uuid4()),
            'type': 'sensor',
            'tenant_id': tenant_id,
            'broker_id': broker_id,
            'sensor_id': sensor_id,
            'iat': now,
            'exp': now + timedelta(minutes=self.ttl_minutes),
        }
        return jwt.encode(payload, self.secret, algorithm=ALGORITHM), expires_in

    def decode(self, token: str) -> dict:
        return _decode(token, self.secret, SENSOR_CLAIMS, 'sensor')


class AgentTokenService:
    """Issue and validate tokens for the IDS agent that posts alerts."""

    def __init__(self, secret: str, ttl_minutes: int = 10080):
        self.secret = secret
        self.ttl_minutes = ttl_minutes

    def create(self, tenant_id: str | None = None) -> tuple[str, int]:
        now = datetime.now(timezone.utc)
        expires_in = self.ttl_minutes * 60
        payload = {
            'sub': 'agent',
            'jti': str(uuid4()),
            'type': 'agent',
            'iat': now,
            'exp': now + timedelta(minutes=self.ttl_minutes),
        }
        if tenant_id:
            payload['tenant_id'] = tenant_id
        return jwt.encode(payload, self.secret, algorithm=ALGORITHM), expires_in

    def decode(self, token: str) -> dict:
        return _decode(token, self.secret, ACCESS_CLAIMS, 'agent')


class RenewingAgentToken:
    """Callable that returns a valid agent token, re-issuing it before expiry."""

    def __init__(self, secret: str, ttl_minutes: int = 60,
                 renew_before_seconds: int = 300, clock=None):
        import time

        self._service = AgentTokenService(secret, ttl_minutes)
        self._renew_before = renew_before_seconds
        self._clock = clock or time.time
        self._token = ''
        self._expires_at = 0.0

    def __call__(self) -> str:
        now = self._clock()
        if now >= self._expires_at - self._renew_before:
            self._token, expires_in = self._service.create()
            self._expires_at = now + expires_in
        return self._token


def main(argv=None) -> int:
    """Print a sensor or agent JWT for local/ops use."""
    parser = argparse.ArgumentParser(description='Issue a sensor or agent JWT')
    parser.add_argument('--agent', action='store_true',
                        help='Issue an agent token instead of a sensor token')
    parser.add_argument('--tenant-id')
    parser.add_argument('--broker-id')
    parser.add_argument('--sensor-id')
    parser.add_argument('--ttl-minutes', type=int, default=10080)
    args = parser.parse_args(argv)
    secret = os.getenv('AUTH_JWT_SECRET')
    if not secret:
        print('AUTH_JWT_SECRET no está configurado', file=sys.stderr)
        return 2
    if args.agent:
        token, _ = AgentTokenService(secret, args.ttl_minutes).create(
            args.tenant_id)
    else:
        missing = [name for name, value in (
            ('tenant-id', args.tenant_id), ('broker-id', args.broker_id),
            ('sensor-id', args.sensor_id)) if not value]
        if missing:
            print(f'faltan: {", ".join(missing)}', file=sys.stderr)
            return 2
        token, _ = SensorTokenService(secret, args.ttl_minutes).create(
            args.tenant_id, args.broker_id, args.sensor_id)
    print(token)
    return 0


if __name__ == '__main__':
    sys.exit(main())
