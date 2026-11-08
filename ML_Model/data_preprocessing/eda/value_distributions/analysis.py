"""Distribución de valores observados de una columna por clase."""

from ..common import TARGET_COL


def values_by_class(df, column):
    """Distribución de valores no nulos de una columna por clase (% dentro de clase)."""
    import pandas as pd

    present = df[column].notna()
    counts = pd.crosstab(df.loc[present, column], df.loc[present, TARGET_COL])
    return counts.join((100 * counts / counts.sum()).round(2).add_prefix('pct_'))
