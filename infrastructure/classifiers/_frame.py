from __future__ import annotations

from typing import Sequence

from application.ports.types import FeatureRow
from infrastructure.tshark.tshark_schema import FEATURE_COLUMNS


def to_frame(window: Sequence[FeatureRow]):
    """Convert feature rows to a DataFrame with the canonical column order."""
    import pandas as pd

    df = pd.DataFrame(list(window))
    if df.empty:
        return pd.DataFrame(columns=list(FEATURE_COLUMNS))
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[list(FEATURE_COLUMNS)]
