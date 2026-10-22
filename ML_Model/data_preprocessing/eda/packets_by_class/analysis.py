"""Reparto de tipos de paquete MQTT dentro de cada clase."""

from ..common import TARGET_COL, packet_types


def packet_type_by_class(df):
    """Frames por tipo de paquete y clase, en conteo y % dentro de cada clase."""
    import pandas as pd

    counts = pd.crosstab(packet_types(df), df[TARGET_COL])
    pct = (100 * counts / counts.sum()).round(3).add_prefix('pct_')
    table = counts.join(pct)
    return table.sort_values(list(counts.columns), ascending=False)
