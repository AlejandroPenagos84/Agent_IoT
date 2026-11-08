"""Gráfica del rol del puerto MQTT por clase."""

from ..common import get_plt, pct_columns


def plot_port_role_by_class(table):
    """Barras apiladas al 100%: rol del puerto MQTT dentro de cada clase."""
    plt = get_plt()

    ax = pct_columns(table).T.plot.bar(stacked=True, figsize=(6, 4), rot=0)
    ax.set(ylabel='% de frames de la clase', title='Rol del puerto 1883/8883 por clase')
    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.show()
