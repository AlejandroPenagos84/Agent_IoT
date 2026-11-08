"""Reglas triviales sin modelo: la línea base que cualquier set debe superar."""

from .metrics import classification_metrics
from .scope import MQTT_PORTS


def trivial_rule_table(df, labels):
    """Una fila por regla, ordenadas por macro-F1 (la primera es la línea base)."""
    import numpy as np
    import pandas as pd

    ports = df[['tcp.srcport', 'tcp.dstport']].apply(pd.to_numeric, errors='coerce')
    to_broker = ports['tcp.dstport'].isin(MQTT_PORTS).astype(int).to_numpy()
    from_broker = ports['tcp.srcport'].isin(MQTT_PORTS).astype(int).to_numpy()
    has_mqtt = df['mqtt.hdrflags'].notna().astype(int).to_numpy()
    rules = {
        'siempre normal': np.zeros(len(labels), dtype=int),
        'siempre DoS': np.ones(len(labels), dtype=int),
        'cliente -> broker': to_broker,
        'broker -> cliente': from_broker,
        'capa MQTT': has_mqtt,
        'cliente -> broker o capa MQTT': np.maximum(to_broker, has_mqtt),
    }
    keep = ['macro_f1', 'balanced_accuracy', 'dos_recall', 'dos_precision']
    rows = [{'regla': name, **{k: v for k, v in classification_metrics(labels, pred).items()
                               if k in keep}}
            for name, pred in rules.items()]
    return (pd.DataFrame(rows).sort_values('macro_f1', ascending=False)
            .set_index('regla'))
