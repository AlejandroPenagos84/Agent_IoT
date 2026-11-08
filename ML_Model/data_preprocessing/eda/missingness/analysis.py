"""Nulos por columna: describe la captura, no decide descartes."""

from ..common import captured_columns


def missingness_report(df):
    """Nulos, no nulos y valores distintos por columna capturada (sin decidir)."""
    import pandas as pd

    if df.empty:
        raise ValueError('Cannot assess missingness in an empty DataFrame')
    columns = captured_columns(df)
    report = pd.DataFrame({
        'column': columns,
        'non_null_count': [int(df[c].notna().sum()) for c in columns],
        'n_unique': [int(df[c].nunique(dropna=True)) for c in columns],
    })
    report['missing_count'] = len(df) - report['non_null_count']
    report['missing_pct'] = (100 * report['missing_count'] / len(df)).round(2)
    return report.sort_values(['missing_count', 'column'], ascending=[False, True]) \
        .reset_index(drop=True)
