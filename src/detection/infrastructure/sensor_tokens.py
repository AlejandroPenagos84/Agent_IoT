"""Sensor JWTs: identify one capture installation. User tokens belong to auth."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

ALGORITHM = 'HS256'
ACCESS_CLAIMS = ('exp', 'iat', 'sub', 'jti', 'type')
SENSOR_CLAIMS = ACCESS_CLAIMS + ('tenant_id', 'broker_id', 'sensor_id')


class TokenError(ValueError):
    """Raised when a JWT is missing, expired, malformed or of the wrong type."""


def _decode(
    token: str, secret: str, required: tuple[str, ...], expected_type: str | None = None
) -> dict:
    try:
        payload = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={'require': list(required)}
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError('token ha expirado') from exc
    except jwt.MissingRequiredClaimError as exc:
        raise TokenError('token incompleto') from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError('token inválido') from exc
    if expected_type is not None and payload.get('type') != expected_type:
        raise TokenError('tipo de token incorrecto')
    return payload


class SensorTokenService:
    """Issue and validate long-lived tokens that identify one capture sensor."""

    def __init__(self, secret: str, ttl_minutes: int = 10080):
        self.secret = secret
        self.ttl_minutes = ttl_minutes

    def create(self, tenant_id: str, broker_id: str, sensor_id: str) -> tuple[str, int]:
        now = datetime.now(UTC)
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


def main(argv=None) -> int:
    """Print a sensor JWT for local/ops use."""
    parser = argparse.ArgumentParser(description='Issue a sensor JWT')
    parser.add_argument('--tenant-id', required=True)
    parser.add_argument('--broker-id', required=True)
    parser.add_argument('--sensor-id', required=True)
    parser.add_argument('--ttl-minutes', type=int, default=10080)
    args = parser.parse_args(argv)
    secret = os.getenv('AUTH_JWT_SECRET')
    if not secret:
        print('AUTH_JWT_SECRET no está configurado', file=sys.stderr)
        return 2
    token, _ = SensorTokenService(secret, args.ttl_minutes).create(
        args.tenant_id, args.broker_id, args.sensor_id
    )
    print(token)
    return 0


if __name__ == '__main__':
    sys.exit(main())
