"""Punto de entrada: ``python -m app`` o ``uvicorn app.main:create_app --factory``."""

from app.composition_root import create_app

__all__ = ['create_app']
