"""Validación cruzada con predicciones out-of-fold (OOF) de un solo set."""

from .metrics import classification_metrics, false_positive_by_capture
from .models import fit_balanced


def cross_validate_oof(features, labels, captures, splits, seed=42):
    """``(folds, oof_prediction, oof_probability, importances)``.

    Cada frame recibe la predicción del modelo que no lo vio al entrenar, así que
    se pueden calcular métricas sobre cualquier subconjunto (p. ej. la vista `mqtt`).
    """
    import numpy as np
    import pandas as pd

    prediction = np.full(len(labels), -1, dtype=int)
    probability = np.full(len(labels), np.nan)
    rows, importances = [], []
    for fold, (train, test) in enumerate(splits):
        model = fit_balanced(features.iloc[train], labels[train], seed)
        prediction[test] = model.predict(features.iloc[test])
        probability[test] = model.predict_proba(features.iloc[test])[:, 1]
        rows.append({'fold': fold,
                     **classification_metrics(labels[test], prediction[test], probability[test]),
                     **false_positive_by_capture(labels[test], prediction[test], captures[test])})
        importances.append(pd.Series(model.feature_importances_, index=features.columns))
    if (prediction < 0).any():
        raise ValueError('Los folds no cubren todas las filas')
    return pd.DataFrame(rows).set_index('fold'), prediction, probability, importances


def subset_metrics(labels, prediction, probability, captures, masks):
    """Métricas OOF de cada subconjunto ``{nombre: máscara booleana}``."""
    import pandas as pd

    rows = {}
    for name, mask in masks.items():
        rows[name] = {'frames': int(mask.sum()), 'DoS': int(labels[mask].sum()),
                      **classification_metrics(labels[mask], prediction[mask], probability[mask]),
                      **false_positive_by_capture(labels[mask], prediction[mask], captures[mask])}
    return pd.DataFrame(rows).T


def confusion_table(labels, prediction, names=('normal', 'DoS')):
    """Matriz de confusión con conteos y % por fila real."""
    import pandas as pd
    from sklearn.metrics import confusion_matrix

    matrix = confusion_matrix(labels, prediction, labels=[0, 1])
    counts = pd.DataFrame(matrix, index=[f'real {n}' for n in names],
                          columns=[f'pred {n}' for n in names])
    share = (100 * counts.div(counts.sum(axis=1), axis=0)).round(2)
    return counts, share
