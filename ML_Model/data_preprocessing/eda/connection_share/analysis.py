"""Fracción de cada tipo de paquete por conexión (evidencia para DERIVE)."""

from ..common import TARGET_COL, packet_types


def connection_packet_share(df, packet_type):
    """Por conexión: fracción de frames de ``packet_type`` y clase mayoritaria."""
    import pandas as pd

    data = pd.DataFrame({
        'connection': df['_connection'].map(str),
        'is_type': packet_types(df).eq(packet_type),
        'label': df[TARGET_COL],
    })
    grouped = data.groupby('connection', sort=False)
    return pd.DataFrame({
        'frames': grouped.size(),
        'count': grouped['is_type'].sum().astype(int),
        'share': grouped['is_type'].mean(),
        'label': grouped['label'].agg(lambda s: s.mode().iloc[0]),
    })
