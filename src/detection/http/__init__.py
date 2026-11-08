"""HTTP entrypoint (FastAPI) for natural-language reports."""

from .app import create_app
from .settings import ApiSettings

__all__ = ["ApiSettings", "create_app"]
