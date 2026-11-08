"""Parse timestamps received as query or body parameters."""

from __future__ import annotations

import math
from datetime import datetime

from fastapi import HTTPException, status


def parse_instant(value: str | None, name: str) -> float | None:
    """Return epoch seconds for an epoch number or a timezone-aware ISO-8601 string."""
    if value is None:
        return None
    candidate = value.strip()
    try:
        number = float(candidate)
    except ValueError:
        number = None
    if number is not None:
        if not math.isfinite(number):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f'{name} debe ser un número finito')
        return number
    try:
        parsed = datetime.fromisoformat(candidate.replace('Z', '+00:00'))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'{name} debe ser epoch o ISO-8601') from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'{name} debe incluir zona horaria')
    return parsed.timestamp()
