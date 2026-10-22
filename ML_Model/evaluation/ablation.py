"""Ablaciones de B y diagnóstico univariado de atajos."""

MATERIAL_DROP = 0.03
MINOR_DROP = 0.01


def ablation_sets(features, removals):
    """``{nombre: matriz}`` con B completo y una variante por cada lista de ``removals``."""
    sets = {'B': features}
    for columns in removals:
        missing = set(columns) - set(features.columns)
        if missing:
            raise ValueError(f'Features inexistentes: {sorted(missing)}')
        sets['B sin ' + ' y '.join(columns)] = features.drop(columns=list(columns))
    return sets


def ablation_deltas(means, reference='B', metric='macro_f1'):
    """Caída de ``metric`` de cada variante frente a ``reference`` y frente a A."""
    import pandas as pd

    rows = []
    for name, value in means[metric].items():
        row = {'set': name, metric: value, f'caída vs {reference}': means.loc[reference, metric]
               - value}
        if 'A' in means.index:
            row['ventaja sobre A'] = value - means.loc['A', metric]
        if name == reference:
            row['lectura'] = 'referencia'
        elif name.startswith(f'{reference} sin'):
            row['lectura'] = interpret_drop(row[f'caída vs {reference}'])
        else:
            row['lectura'] = 'comparación (no es ablación)'
        rows.append(row)
    return pd.DataFrame(rows).set_index('set')


def interpret_drop(drop):
    """Texto del criterio del plan: > 0,03 depende; > 0,01 pierde algo; si no, robusto."""
    if drop > MATERIAL_DROP:
        return 'depende materialmente de lo quitado'
    if drop > MINOR_DROP:
        return 'pierde algo, no crítico'
    return 'robusto: la señal está repartida'


def univariate_auc(labels, scores):
    """``(AUC en la mejor dirección, '+'|'-'|'constante')``."""
    import numpy as np
    from sklearn.metrics import roc_auc_score

    scores = np.asarray(scores, dtype=float)
    if len(np.unique(scores)) < 2 or len(np.unique(labels)) < 2:
        return 0.5, 'constante'
    auc = float(roc_auc_score(labels, scores))
    return max(auc, 1.0 - auc), '+' if auc >= 0.5 else '-'


def univariate_auc_table(views):
    """AUC univariada de cada feature en cada vista ``{nombre: (X, labels)}``.

    Una feature con AUC alta en todo el tráfico y baja en la vista `mqtt` separa
    "normal no-MQTT" de "DoS MQTT": es atajo de protocolo, no señal de DoS.
    """
    import pandas as pd

    columns = list(next(iter(views.values()))[0].columns)
    rows = []
    for feature in columns:
        row = {'feature': feature}
        for name, (features, labels) in views.items():
            row[f'AUC {name}'], row[f'dir {name}'] = univariate_auc(labels, features[feature])
        rows.append(row)
    table = pd.DataFrame(rows).set_index('feature')
    names = list(views)
    if len(names) == 2:
        table['caída'] = table[f'AUC {names[0]}'] - table[f'AUC {names[1]}']
    return table.sort_values(f'AUC {names[-1]}', ascending=False)
