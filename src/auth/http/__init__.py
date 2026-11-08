"""Capa HTTP del módulo auth."""

from auth.http.errors import ERROR_MAP, register_exception_handlers, resolve_error

__all__ = ["ERROR_MAP", "register_exception_handlers", "resolve_error"]
