"""Resumen gráfico de la tabla de política."""

from ..common import get_plt


def plot_policy_summary(policy):
    """Cuántas columnas reciben cada motivo, apiladas por acción."""
    plt = get_plt()
    import pandas as pd

    counts = pd.crosstab(policy['motivo'], policy['acción'])
    ax = counts.sort_values(list(counts.columns), ascending=False).plot.barh(
        stacked=True, figsize=(7, 4))
    ax.set(xlabel='nº de columnas', ylabel='motivo', title='Política: motivo × acción')
    ax.set_xlim(0, counts.sum(axis=1).max() * 1.08)
    for container in ax.containers:
        ax.bar_label(container, label_type='center', fontsize=8,
                     labels=[int(v) if v else '' for v in container.datavalues])
    plt.tight_layout()
    plt.show()
