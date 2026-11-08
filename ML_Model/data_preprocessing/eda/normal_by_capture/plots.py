"""Gráfica del normal por captura y de la regla trivial por alcance."""

from ..common import get_plt


def plot_normal_by_capture(profile, rule_comparison):
    """% MQTT/PUBLISH del normal por captura y métricas de "puerto MQTT => DoS"."""
    plt = get_plt()

    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    profile[['% puerto MQTT', '% capa MQTT', '% PUBLISH']].plot.bar(ax=axes[0], rot=0)
    axes[0].set(ylabel='% de frames normales', xlabel='captura de origen',
                title='Tráfico normal por captura')
    for container in axes[0].containers:
        axes[0].bar_label(container, fmt='%.1f', fontsize=7)
    rule_comparison[['balanced_accuracy', 'precision_DoS', 'macro_f1']].T.plot.bar(
        ax=axes[1], rot=0)
    axes[1].set(ylim=(0, 1.05), title='Regla "puerto MQTT => DoS"')
    axes[1].legend(fontsize=8, loc='lower left')
    fig.tight_layout()
    plt.show()
