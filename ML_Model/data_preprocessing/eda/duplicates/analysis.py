"""Columnas idénticas celda a celda (motivo DUPLICATE)."""

from ..common import captured_columns


def duplicate_columns(df, columns=None, preferred=()):
    """Columnas idénticas a otra en el 100% de filas (nulos incluidos).

    Devuelve un DataFrame indexado por la columna duplicada con ``duplicate_of``,
    la columna que se conserva (la primera de ``preferred`` o del orden original).
    """
    import pandas as pd

    columns = [c for c in (columns or captured_columns(df)) if df[c].notna().any()]
    groups = {}
    for column in columns:
        key = tuple(df[column].astype('string').fillna('<NA>'))
        groups.setdefault(hash(key), []).append((column, key))
    rows = []
    for members in groups.values():
        while members:
            column, key = members[0]
            same = [c for c, k in members if k == key]
            members = [(c, k) for c, k in members if k != key]
            if len(same) < 2:
                continue
            kept = next((c for c in preferred if c in same), same[0])
            rows += [{'column': c, 'duplicate_of': kept} for c in same if c != kept]
    return pd.DataFrame(rows, columns=['column', 'duplicate_of']).set_index('column')
