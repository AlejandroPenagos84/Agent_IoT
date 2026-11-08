"""tshark capture and JSONL frame source adapters."""

__all__ = ["TsharkFeatureSource"]


def __getattr__(name):
    """Load the agent adapter only when explicitly requested.

    The capture sidecar runs this package without application/domain installed.
    """
    if name == 'TsharkFeatureSource':
        from .tshark_feature_source import TsharkFeatureSource
        return TsharkFeatureSource
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
