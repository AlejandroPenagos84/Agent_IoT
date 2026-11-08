"""Gráfica de nulos por columna, opcionalmente coloreada por motivo."""

from ..common import get_plt


def plot_missingness(report, policy=None):
    """% de nulos por columna; si se pasa la política, el color es el motivo."""
    plt = get_plt()
    from matplotlib.patches import Patch

    ordered = report.iloc[::-1]
    if policy is None:
        colors = ['#4e79a7'] * len(ordered)
        legend = []
    else:
        motive = policy.set_index('columna')['motivo']
        palette = dict(zip(sorted(motive.unique()), plt.cm.tab10.colors))
        colors = [palette[motive[c]] for c in ordered['column']]
        legend = [Patch(color=palette[m], label=m) for m in palette]
    fig, ax = plt.subplots(figsize=(10, max(5, len(ordered) * 0.27)))
    ax.barh(ordered['column'], ordered['missing_pct'], color=colors)
    # Marcador del motivo a la izquierda: visible también en columnas sin nulos.
    ax.barh(ordered['column'], 3, left=-4, color=colors)
    ax.axvline(0, color='black', lw=0.6)
    ax.set(xlabel='Valores nulos (%)', xlim=(-5, 105), ylim=(-0.7, len(ordered) - 0.3),
           title='Nulos por columna (color = motivo de la política)')
    if legend:
        ax.legend(handles=legend, loc='lower right')
    fig.tight_layout()
    plt.show()
