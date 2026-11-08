"""Barras de los valores más frecuentes por clase."""

from ..common import get_plt, pct_columns
from .analysis import values_by_class


def plot_values_by_class(df, columns, top=8):
    """Barras de los valores más frecuentes de columnas categóricas por clase."""
    plt = get_plt()

    fig, axes = plt.subplots(1, len(columns), figsize=(5 * len(columns), 4), squeeze=False)
    for ax, column in zip(axes[0], columns):
        pct = pct_columns(values_by_class(df, column))
        pct = pct.loc[pct.max(axis=1).sort_values(ascending=False).index[:top]]
        pct.plot.bar(ax=ax, rot=0)
        ax.set(title=f'{column} (solo no nulos)', xlabel='valor',
               ylabel='% de no nulos de la clase')
    fig.tight_layout()
    plt.show()
