"""Folds agrupados por conexión con ambas clases y normal de todas las capturas."""


def _valid(labels, captures, indices, required):
    import numpy as np

    if len(np.unique(labels[indices])) < 2:
        return False
    return required.issubset(set(captures[indices][labels[indices] == 0]))


def find_grouped_splits(labels, groups, captures, required_normal_captures,
                        max_splits=5, seed=42):
    """``(n_splits, splits)``: el mayor nº de folds (≤ ``max_splits``) válido.

    Un fold es válido si train y test tienen ambas clases y normal de todas las
    capturas requeridas. Se reduce el nº de folds hasta encontrarlo.
    """
    import numpy as np
    from sklearn.model_selection import StratifiedGroupKFold

    required = set(required_normal_captures)
    placeholder = np.zeros(len(labels))
    for n_splits in range(max_splits, 1, -1):
        splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        splits = list(splitter.split(placeholder, labels, groups=groups))
        if all(_valid(labels, captures, part, required)
               for train, test in splits for part in (train, test)):
            return n_splits, splits
    raise ValueError('No hay folds agrupados con ambas clases y normal de todas las '
                     f'capturas. Capturas requeridas: {sorted(required)}')


def fold_composition(labels, captures, splits):
    """Tamaño de cada fold y normal de test por captura de origen."""
    import pandas as pd

    rows = []
    for fold, (train, test) in enumerate(splits):
        normal_test = pd.Series(captures[test][labels[test] == 0]).value_counts()
        rows.append({'fold': fold, 'train': len(train), 'test': len(test),
                     'DoS_test': int(labels[test].sum()),
                     **{f'normal_test_{c}': int(n) for c, n in normal_test.sort_index().items()}})
    return pd.DataFrame(rows).set_index('fold').fillna(0).astype(int)
