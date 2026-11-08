from __future__ import annotations

import json
import math
import os
from collections import Counter

SEQ_LEN = 10
NAN_FILL = -1.0

# Red/transporte crudo que se conserva. `frame.time_relative` (fuga de captura),
# `frame.cap_len` (igual a frame.len) y `frame.time_delta_displayed` (igual a
# frame.time_delta) se descartan.
COLS_RED = ['frame.len', 'frame.time_delta']

# Campos MQTT crudos con senal. `mqtt.hdrflags` ya codifica msgtype/qos/retain/dupflag.
MQTT_NUMERIC_COLUMNS = ['mqtt.hdrflags', 'mqtt.len', 'mqtt.topic_len']

# Orden final de la matriz del notebook; debe coincidir con pipeline_config.json.
MODEL_FEATURES = [
    'frame.len', 'frame.time_delta',
    'fe_bytes_per_sec', 'fe_is_standard_mqtt_port', 'fe_is_broker_to_client', 'fe_log_len',
    'mqtt.hdrflags', 'mqtt.len', 'mqtt.topic_len',
    'fe_msg_entropy', 'fe_topic_entropy', 'fe_topic_depth', 'fe_payload_ratio',
]


def load_config(model_dir: str) -> dict:
    """Load the exported pipeline contract from a model directory."""
    with open(os.path.join(model_dir, 'pipeline_config.json')) as handle:
        return json.load(handle)


def select_features(df, cols, where: str):
    """Select columns in pipeline order and fail clearly when any are missing."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(
            f'{where}: faltan columnas requeridas por pipeline_config.json: '
            f'{missing}. Columnas disponibles: {list(df.columns)}')
    return df[list(cols)].copy()


def validate_named_features(expected, actual, where: str) -> None:
    """Ensure an exported model exposes exactly the configured feature names."""
    if actual is None:
        raise ValueError(
            f'{where}: el artefacto no expone nombres de features; '
            'no se puede verificar contra pipeline_config.json')
    expected = list(expected)
    actual = list(actual)
    if expected != actual:
        raise ValueError(
            f'{where}: las features de pipeline_config.json no coinciden con '
            f'el modelo exportado.\n'
            f'  config ({len(expected)}): {expected}\n'
            f'  modelo ({len(actual)}): {actual}\n'
            'Reentrena y reexporta modelos_agente/ desde ml-mqtt-model.ipynb.')
    return None


def entropia(texto) -> float:
    """Compute Shannon entropy for a text value."""
    import pandas as pd

    if pd.isna(texto) or not str(texto):
        return 0.0
    cadena = str(texto)
    probs = [c / len(cadena) for c in Counter(cadena).values()]
    return -sum(p * math.log2(p) for p in probs)


def build_network_features(df):
    """Network/transport subset without raw ports, capture clock or duplicates."""
    import numpy as np
    import pandas as pd

    base = df[[c for c in COLS_RED if c in df.columns]].copy()
    for c in COLS_RED:
        if c not in base.columns:
            base[c] = np.nan
    base = base[COLS_RED]
    for c in base.columns:
        base[c] = pd.to_numeric(base[c], errors='coerce').fillna(NAN_FILL)

    base['fe_bytes_per_sec'] = base['frame.len'] / (base['frame.time_delta'] + 1e-6)
    dst = (pd.to_numeric(df['tcp.dstport'], errors='coerce')
           if 'tcp.dstport' in df.columns else pd.Series(0, index=df.index))
    src = (pd.to_numeric(df['tcp.srcport'], errors='coerce')
           if 'tcp.srcport' in df.columns else pd.Series(0, index=df.index))
    base['fe_is_standard_mqtt_port'] = dst.isin([1883, 8883]).astype(int)
    base['fe_is_broker_to_client'] = src.isin([1883, 8883]).astype(int)
    base['fe_log_len'] = np.log1p(base['frame.len'])
    return base


def build_mqtt_features(df):
    """Matriz compacta MQTT: red + campos MQTT con senal + derivadas de entropia."""
    import numpy as np
    import pandas as pd

    result = build_network_features(df)

    def number(value):
        if isinstance(value, str) and value.lower().startswith('0x'):
            try:
                return int(value, 16)
            except ValueError:
                return np.nan
        return value

    for col in MQTT_NUMERIC_COLUMNS:
        series = df[col] if col in df else pd.Series(np.nan, index=df.index)
        result[col] = pd.to_numeric(series.map(number), errors='coerce').fillna(NAN_FILL)
    msg = df['mqtt.msg'] if 'mqtt.msg' in df else pd.Series(None, index=df.index, dtype=object)
    topic = df['mqtt.topic'] if 'mqtt.topic' in df else pd.Series(None, index=df.index, dtype=object)
    result['fe_msg_entropy'] = msg.apply(entropia)
    result['fe_topic_entropy'] = topic.apply(entropia)
    result['fe_topic_depth'] = topic.apply(
        lambda value: 0 if pd.isna(value) or not str(value) else str(value).count('/') + 1)
    result['fe_payload_ratio'] = result['mqtt.len'].clip(lower=0) / (
        result['frame.len'].clip(lower=0) + 1e-5)
    return result.replace([np.inf, -np.inf], NAN_FILL).fillna(NAN_FILL)[MODEL_FEATURES]


def build_case1(df, cfg: dict):
    """Select the compact MQTT feature set for the binary XGBoost model."""
    return select_features(build_mqtt_features(df), cfg['feature_columns_case1'],
                           'XgbClassifier MQTT')


def build_lstm_raw(df, cfg: dict):
    """Select the configured MQTT feature set for the LSTM."""
    return select_features(build_mqtt_features(df),
                           cfg['feature_columns_lstm_raw'], 'build_lstm_raw')


def crear_secuencias(data, seq_length: int = SEQ_LEN):
    """Build overlapping sequences and their final-row indices."""
    import numpy as np

    xs, end_idx = [], []
    for i in range(len(data) - seq_length + 1):
        xs.append(data[i:i + seq_length])
        end_idx.append(i + seq_length - 1)
    return np.array(xs), np.array(end_idx)


def recon_mse(lstm, xs, device, batch_size: int = 1024):
    """Compute batched LSTM reconstruction mean squared errors."""
    import numpy as np
    import torch

    mse_all = []
    with torch.no_grad():
        for i in range(0, len(xs), batch_size):
            batch = torch.tensor(xs[i:i + batch_size], dtype=torch.float32).to(device)
            out = lstm(batch)
            mse_all.append(torch.mean((out - batch) ** 2, dim=[1, 2]).cpu().numpy())
    return np.concatenate(mse_all) if mse_all else np.array([])
