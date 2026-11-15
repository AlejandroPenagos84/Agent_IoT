"""Secretos de inscripción: claves de broker y secretos de sensor.

Son secretos aleatorios de 256 bits; en la base solo se guarda su SHA-256 (con
esa entropía no hace falta un hash lento como el de las contraseñas).
"""

from __future__ import annotations

import hashlib
import secrets

ENROLLMENT_PREFIX = 'ek_'
SENSOR_SECRET_PREFIX = 'ss_'


def new_secret(prefix: str) -> str:
    """Secreto aleatorio de 256 bits con un prefijo reconocible."""
    return prefix + secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    """SHA-256 del secreto: lo único que se persiste."""
    return hashlib.sha256(value.encode('utf-8')).hexdigest()
