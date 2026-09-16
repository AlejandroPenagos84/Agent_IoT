from __future__ import annotations

from typing import Sequence

import pandas as pd

from core.types import FEATURE_COLUMNS, FeatureRow


def to_frame(window: Sequence[FeatureRow]) -> pd.DataFrame:
    df = pd.DataFrame(list(window))
    if df.empty:
        return pd.DataFrame(columns=list(FEATURE_COLUMNS))
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    return df[list(FEATURE_COLUMNS)]
