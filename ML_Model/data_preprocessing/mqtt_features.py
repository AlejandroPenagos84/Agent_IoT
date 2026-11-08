"""Features de la opción A (13 features, MQTT en claro).

Se conserva solo como referencia experimental para `02_tcp_vs_mqtt.ipynb`: el
modelo final usa `tcp_features.py` (opción B). Espejo de las celdas originales
`build_network_features` / `build_mqtt_features` del notebook monolítico.
"""

from .feature_engineering import FEATURE_COLUMNS, entropy

NAN_FILL = -1.0
MQTT_PORTS = (1883, 8883)
NETWORK_RAW = ['frame.len', 'frame.time_delta']
MQTT_NUMERIC_COLUMNS = ['mqtt.hdrflags', 'mqtt.len', 'mqtt.topic_len']


def _number(value):
    """'0x30' -> 48; el resto se deja para pd.to_numeric."""
    import numpy as np

    if isinstance(value, str) and value.lower().startswith('0x'):
        try:
            return int(value, 16)
        except ValueError:
            return np.nan
    return value


def build_network_features(df):
    """Red/transporte sin puertos crudos ni timestamps de captura."""
    import numpy as np
    import pandas as pd

    base = df[NETWORK_RAW].apply(pd.to_numeric, errors='coerce').fillna(NAN_FILL).copy()
    # Fórmula instantánea del notebook original (no la causal del agente).
    base['fe_bytes_per_sec'] = base['frame.len'] / (base['frame.time_delta'] + 1e-6)
    dst = pd.to_numeric(df['tcp.dstport'], errors='coerce')
    src = pd.to_numeric(df['tcp.srcport'], errors='coerce')
    base['fe_is_standard_mqtt_port'] = dst.isin(MQTT_PORTS).astype(int)
    base['fe_is_broker_to_client'] = src.isin(MQTT_PORTS).astype(int)
    base['fe_log_len'] = np.log1p(base['frame.len'])
    return base


def build_mqtt_features(df):
    """Red + campos MQTT numéricos, entropías y estructura del topic."""
    import numpy as np
    import pandas as pd

    result = build_network_features(df)
    for column in MQTT_NUMERIC_COLUMNS:
        series = df[column] if column in df else pd.Series(np.nan, index=df.index)
        result[column] = pd.to_numeric(series.map(_number), errors='coerce').fillna(NAN_FILL)
    empty = pd.Series(None, index=df.index, dtype=object)
    msg = df['mqtt.msg'] if 'mqtt.msg' in df else empty
    topic = df['mqtt.topic'] if 'mqtt.topic' in df else empty
    result['fe_msg_entropy'] = msg.apply(entropy)
    result['fe_topic_entropy'] = topic.apply(entropy)
    result['fe_topic_depth'] = topic.apply(
        lambda v: 0 if pd.isna(v) or not str(v) else str(v).count('/') + 1)
    result['fe_payload_ratio'] = result['mqtt.len'].clip(lower=0) / (
        result['frame.len'].clip(lower=0) + 1e-5)
    return result.replace([np.inf, -np.inf], NAN_FILL).fillna(NAN_FILL)


def build_feature_matrix(df):
    """Matriz A en el orden de `FEATURE_COLUMNS`."""
    return build_mqtt_features(df)[FEATURE_COLUMNS]
