"""Rol del puerto MQTT (1883/8883) en cada frame, por clase."""

from ..common import MQTT_PORTS, TARGET_COL


def port_role_by_class(df):
    """Frames hacia el broker, desde el broker o sin puerto MQTT, por clase."""
    import numpy as np
    import pandas as pd

    src = pd.to_numeric(df['tcp.srcport'], errors='coerce').isin(MQTT_PORTS)
    dst = pd.to_numeric(df['tcp.dstport'], errors='coerce').isin(MQTT_PORTS)
    role = pd.Series(np.select([dst, src], ['cliente -> broker', 'broker -> cliente'],
                               'sin puerto MQTT'), index=df.index, name='port_role')
    counts = pd.crosstab(role, df[TARGET_COL])
    return counts.join((100 * counts / counts.sum()).round(2).add_prefix('pct_'))
