"""Sensibilidad aproximada a MQTTS: padding TLS sobre `frame.len` en test."""

from .models import fit_balanced


def tls_padding_sensitivity(features, labels, splits, mqtt_layer,
                            padding_min=21, padding_max=40, seed=42):
    """Macro-F1 de cada fold antes y después de sumar 21–40 bytes a los frames MQTT.

    Solo se perturba test (el modelo se entrena sin padding) y se recalcula
    ``fe_log_len``. Las ventanas TCP que dependen de bytes no se recalculan, así
    que es una cota optimista de la caída.
    """
    import numpy as np
    import pandas as pd
    from sklearn.metrics import f1_score

    rng = np.random.default_rng(seed)
    rows = []
    for fold, (train, test) in enumerate(splits):
        model = fit_balanced(features.iloc[train], labels[train], seed)
        base = f1_score(labels[test], model.predict(features.iloc[test]),
                        average='macro', zero_division=0)
        perturbed = features.iloc[test].copy()
        positions = np.where(mqtt_layer[test])[0]
        frame_len = perturbed['frame.len'].to_numpy(dtype=float).copy()
        frame_len[positions] += rng.uniform(padding_min, padding_max + 1, size=len(positions))
        perturbed['frame.len'] = frame_len
        if 'fe_log_len' in perturbed:
            perturbed['fe_log_len'] = np.log1p(frame_len)
        tls = f1_score(labels[test], model.predict(perturbed), average='macro', zero_division=0)
        rows.append({'fold': fold, 'macro_f1_base': float(base), 'macro_f1_tls': float(tls),
                     'caida': float(base - tls), 'frames_mqtt_perturbados': int(len(positions))})
    return pd.DataFrame(rows).set_index('fold')
