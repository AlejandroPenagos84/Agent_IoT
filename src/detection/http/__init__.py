"""HTTP entrypoint (FastAPI) for the detection API."""

from .app import create_app
from .container import RegistryContainer, build_container
from .settings import ApiSettings

__all__ = ["ApiSettings", "RegistryContainer", "build_container", "create_app"]
