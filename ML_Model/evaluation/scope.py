"""Vista `mqtt`: frames con puerto 1883/8883 en origen o destino."""

TARGET_COL = 'type'
ATTACK_LABEL = 'DoS'
MQTT_PORTS = (1883, 8883)


def mqtt_scope(df):
    """Copia de ``df`` con solo frames hacia o desde el puerto MQTT.

    Se filtra por puerto y no por capa MQTT para conservar los SYN/ACK de las
    conexiones MQTT y los frames DoS sin capa MQTT.
    """
    import pandas as pd

    ports = df[['tcp.srcport', 'tcp.dstport']].apply(pd.to_numeric, errors='coerce')
    return df.loc[ports.isin(MQTT_PORTS).any(axis=1)].copy()


def binary_labels(df):
    """1 = DoS, 0 = normal (numpy)."""
    return df[TARGET_COL].eq(ATTACK_LABEL).astype(int).to_numpy()


def normal_captures(df):
    """Capturas que aportan normal a ``df``."""
    return sorted(df.loc[df[TARGET_COL].eq('normal'), '_capture'].unique())


def scope_overview(df):
    """``(frames por captura y clase, conexiones por captura y clase)`` con totales."""
    import pandas as pd

    frames = pd.crosstab(df['_capture'], df[TARGET_COL], margins=True, margins_name='total')
    connections = (df.groupby(['_capture', TARGET_COL])['_connection'].nunique()
                   .unstack(fill_value=0))
    connections.loc['total'] = df.groupby(TARGET_COL)['_connection'].nunique()
    return frames, connections
