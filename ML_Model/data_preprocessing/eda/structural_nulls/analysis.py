"""Regla STRUCTURAL_NULL: paso 1 (alineación) y paso 2 (separación)."""

from ..common import TARGET_COL, attack_label, packet_groups, packet_types


def structural_null_alignment(df, columns, min_jaccard=0.95):
    """Paso 1 de STRUCTURAL_NULL: ¿los no nulos coinciden con un tipo de paquete?

    Para cada columna se busca el grupo (tipo concreto o MQTT) cuyo conjunto de
    frames tiene mayor índice de Jaccard con los frames no nulos. ``precision``
    es la parte de no nulos dentro del grupo; ``coverage``, la parte del grupo
    con valor. ``aligned`` exige Jaccard >= ``min_jaccard``.
    """
    import pandas as pd

    types = packet_types(df)
    groups = packet_groups(types, include_no_mqtt=False)
    rows = []
    for column in columns:
        present = df[column].notna()
        best, score = None, -1.0
        for name, mask in groups.items():
            union = int((present | mask).sum())
            jaccard = int((present & mask).sum()) / union if union else 0.0
            if jaccard > score:
                best, score = name, jaccard
        mask = groups[best]
        by_type = types[present].value_counts()
        rows.append({
            'column': column, 'non_null': int(present.sum()), 'best_group': best,
            'jaccard': round(score, 4),
            'precision': int((present & mask).sum()) / max(int(present.sum()), 1),
            'coverage': int((present & mask).sum()) / max(int(mask.sum()), 1),
            'aligned': score >= min_jaccard,
            'non_null_by_type': ', '.join(f'{k}={v}' for k, v in by_type.head(4).items()),
        })
    return pd.DataFrame(rows).set_index('column')


def packet_type_separation(df, min_ratio=2.0, min_count=10):
    """Paso 2 de STRUCTURAL_NULL: ¿la proporción de un tipo separa DoS de normal?

    ``separates`` exige que la proporción en una clase sea al menos ``min_ratio``
    veces la de la otra y que haya ``min_count`` frames del tipo en total. Incluye
    la fila MQTT (cualquier tipo) para columnas presentes en todo frame MQTT.
    """
    import numpy as np
    import pandas as pd

    is_attack = df[TARGET_COL].eq(attack_label(df))
    n_normal_total, n_attack_total = int((~is_attack).sum()), int(is_attack.sum())
    rows = []
    for name, mask in packet_groups(packet_types(df)).items():
        n_normal, n_attack = int((mask & ~is_attack).sum()), int((mask & is_attack).sum())
        p_normal = 100 * n_normal / n_normal_total
        p_attack = 100 * n_attack / n_attack_total
        low, high = sorted([p_normal, p_attack])
        ratio = np.inf if low == 0 else high / low
        rows.append({
            'group': name, 'count_normal': n_normal, 'count_attack': n_attack,
            'pct_normal': p_normal, 'pct_attack': p_attack, 'ratio': ratio,
            'separates': bool(ratio >= min_ratio and n_normal + n_attack >= min_count),
        })
    return pd.DataFrame(rows).set_index('group').sort_values('ratio', ascending=False)
