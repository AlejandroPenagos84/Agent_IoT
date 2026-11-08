"""tshark capture and asyncio socket server adapters."""

__all__ = ["AsyncSocketServer"]


def __getattr__(name):
    """Load the agent adapter only when explicitly requested.

    The capture sidecar runs this package without application/domain installed.
    """
    if name == 'AsyncSocketServer':
        from .async_socket_server import AsyncSocketServer
        return AsyncSocketServer
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
