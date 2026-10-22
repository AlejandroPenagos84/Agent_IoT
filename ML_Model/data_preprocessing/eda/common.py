"""Constantes y utilidades compartidas por todos los análisis del EDA."""

from ..feature_engineering import INTERNAL_COLUMNS

TARGET_COL = 'type'
NORMAL_LABEL = 'normal'
NO_MQTT = 'NO_MQTT'
MALFORMED = 'MALFORMED'
MQTT_ANY = 'MQTT'
MQTT_PORTS = (1883, 8883)

# Tipo de paquete = bits 7-4 del byte de cabecera fija (MQTT 3.1.1).
MQTT_PACKET_TYPES = {
    0: 'RESERVED_0', 1: 'CONNECT', 2: 'CONNACK', 3: 'PUBLISH', 4: 'PUBACK',
    5: 'PUBREC', 6: 'PUBREL', 7: 'PUBCOMP', 8: 'SUBSCRIBE', 9: 'SUBACK',
    10: 'UNSUBSCRIBE', 11: 'UNSUBACK', 12: 'PINGREQ', 13: 'PINGRESP',
    14: 'DISCONNECT', 15: 'RESERVED_15',
}


def get_plt():
    """Import lazy de matplotlib: el análisis numérico no lo necesita."""
    import matplotlib.pyplot as plt
    return plt


def captured_columns(df):
    """Columnas del CSV, sin la etiqueta ni las claves internas de agrupación."""
    return [name for name in df.columns if name not in INTERNAL_COLUMNS]


def attack_label(df):
    """Única etiqueta distinta de ``normal``; falla si el problema no es binario."""
    labels = sorted(set(df[TARGET_COL].unique()) - {NORMAL_LABEL})
    if NORMAL_LABEL not in set(df[TARGET_COL]) or len(labels) != 1:
        raise ValueError(f'Expected normal plus one attack label, got {labels}')
    return labels[0]


def pct_columns(table):
    """Columnas ``pct_<clase>`` de una tabla, renombradas a ``<clase>``."""
    pct = table[[c for c in table.columns if c.startswith('pct_')]]
    return pct.rename(columns=lambda c: c[4:])


def parse_hdrflags(series):
    """Convierte mqtt.hdrflags ('0x00000030', 48 o nulo) a entero o NaN."""
    import numpy as np
    import pandas as pd

    def parse(value):
        if pd.isna(value):
            return np.nan
        text = str(value).split(',')[0].strip()
        try:
            return int(text, 16) if text.lower().startswith('0x') else int(float(text))
        except ValueError:
            return np.nan
    return series.map(parse).astype(float)


def packet_types(df):
    """Tipo de paquete MQTT por frame; NO_MQTT si el frame no lleva MQTT."""
    flags = parse_hdrflags(df['mqtt.hdrflags'])
    names = flags.map(lambda v: MQTT_PACKET_TYPES[int(v) >> 4] if v == v else NO_MQTT)
    names[df['mqtt.hdrflags'].notna() & flags.isna()] = MALFORMED
    return names.rename('packet_type')


def mqtt_port_masks(df):
    """Máscaras ``(origen 1883/8883, destino 1883/8883)`` por frame."""
    import pandas as pd

    src = pd.to_numeric(df['tcp.srcport'], errors='coerce').isin(MQTT_PORTS)
    dst = pd.to_numeric(df['tcp.dstport'], errors='coerce').isin(MQTT_PORTS)
    return src, dst


def port_role(df):
    """Rol del frame respecto al broker: cliente -> broker, broker -> cliente o ninguno."""
    import numpy as np
    import pandas as pd

    src, dst = mqtt_port_masks(df)
    return pd.Series(np.select([dst, src], ['cliente -> broker', 'broker -> cliente'],
                               'sin puerto MQTT'), index=df.index, name='rol del puerto')


def normal_frames(df):
    """Solo los frames ``normal``."""
    return df[df[TARGET_COL].eq(NORMAL_LABEL)]


def packet_groups(types, include_no_mqtt=True):
    """Máscaras por tipo de paquete más el grupo MQTT (cualquier tipo)."""
    groups = {name: types.eq(name) for name in types.unique()
              if include_no_mqtt or name != NO_MQTT}
    groups[MQTT_ANY] = types.ne(NO_MQTT)
    return groups
