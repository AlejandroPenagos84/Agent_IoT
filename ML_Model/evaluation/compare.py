"""Entrenamiento por fold de varios sets de features con el mismo protocolo."""

from .metrics import classification_metrics, false_positive_by_capture, metric_columns
from .models import fit_balanced


def compare_feature_sets(feature_sets, labels, captures, splits, seed=42):
    """``(folds, importances)`` para ``{nombre: DataFrame de features}``.

    Todos los sets usan los mismos ``splits``, hiperparámetros y pesos.
    ``importances[nombre]`` es la lista de importancias por fold.
    """
    import pandas as pd

    lengths = {name: len(x) for name, x in feature_sets.items()}
    if len(set(lengths.values()) | {len(labels)}) != 1:
        raise ValueError(f'Longitudes distintas: {lengths}, labels={len(labels)}')
    rows, importances = [], {}
    for fold, (train, test) in enumerate(splits):
        for name, features in feature_sets.items():
            model = fit_balanced(features.iloc[train], labels[train], seed)
            prediction = model.predict(features.iloc[test])
            probability = model.predict_proba(features.iloc[test])[:, 1]
            rows.append({'set': name, 'fold': fold,
                         **classification_metrics(labels[test], prediction, probability),
                         **false_positive_by_capture(labels[test], prediction, captures[test])})
            importances.setdefault(name, []).append(
                pd.Series(model.feature_importances_, index=features.columns))
    return pd.DataFrame(rows), importances


def summarize_folds(folds):
    """``(media ± std por set en columnas planas, media por set)``."""
    columns = metric_columns(folds)
    summary = folds.groupby('set', sort=False)[columns].agg(['mean', 'std'])
    summary.columns = [f'{metric}_{stat}' for metric, stat in summary.columns]
    return summary, folds.groupby('set', sort=False)[columns].mean()


def mean_importance(importances):
    """Importancia media por set: DataFrame features x sets (NaN si no aplica)."""
    import pandas as pd

    return pd.DataFrame({name: pd.concat(frames, axis=1).mean(axis=1)
                         for name, frames in importances.items()})
