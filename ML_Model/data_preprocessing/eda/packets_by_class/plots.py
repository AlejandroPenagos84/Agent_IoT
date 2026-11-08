"""Gráfica de tipos de paquete por clase."""

from ..common import get_plt, pct_columns


def plot_packet_type_by_class(table):
    """% de frames de cada tipo dentro de cada clase (eje log: hay tipos raros)."""
    plt = get_plt()

    pct = pct_columns(table).iloc[::-1]
    ax = pct.plot.barh(figsize=(9, max(4, len(pct) * 0.45)), logx=True)
    ax.set(xlabel='% de frames de la clase (escala log)', ylabel='tipo de paquete',
           title='Tipo de paquete MQTT por clase')
    for container in ax.containers:
        ax.bar_label(container, fmt='%.3g%%', fontsize=7, padding=2)
    plt.tight_layout()
    plt.show()
