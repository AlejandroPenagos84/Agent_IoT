"""Boxplots de la fracción de tipos de paquete por conexión."""

from ..common import get_plt
from .analysis import connection_packet_share


def plot_connection_packet_share(df, packet_types_to_plot):
    """Boxplot por clase de la fracción de cada tipo de paquete por conexión."""
    plt = get_plt()

    fig, axes = plt.subplots(1, len(packet_types_to_plot),
                             figsize=(4 * len(packet_types_to_plot), 4), squeeze=False)
    for ax, name in zip(axes[0], packet_types_to_plot):
        share = connection_packet_share(df, name)
        labels = sorted(share['label'].unique())
        ax.boxplot([share.loc[share['label'].eq(l), 'share'] for l in labels],
                   tick_labels=labels, showfliers=True)
        counts = share['label'].value_counts()
        ax.set(title=f'{name} por conexión', ylabel='fracción de frames',
               xlabel=' / '.join(f'{l}: {counts[l]} conexiones' for l in labels))
    fig.tight_layout()
    plt.show()
