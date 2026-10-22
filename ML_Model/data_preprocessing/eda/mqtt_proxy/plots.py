"""Gráfica de la verificación del proxy MQTT = DoS."""

from ..common import get_plt


def plot_mqtt_proxy(proxy_table, baseline, attack_share):
    """Composición de clase por grupo y métricas de las reglas triviales.

    ``attack_share`` es la fracción global de frames de ataque (línea de referencia).
    """
    plt = get_plt()

    fig, axes = plt.subplots(1, 2, figsize=(14, 4), gridspec_kw={'width_ratios': [3, 2]})
    shares = proxy_table[[c for c in proxy_table.columns if c.startswith('% ')
                          and c != '% del total']]
    shares.index = [f'{role} | {layer} (n={n:,})'
                    for (role, layer), n in zip(shares.index, proxy_table['frames'])]
    colors = ['#c0392b' if c != '% normal' else '#4e79a7' for c in shares.columns]
    shares.iloc[::-1].plot.barh(stacked=True, ax=axes[0], color=colors)
    axes[0].axvline(100 * attack_share, color='black', ls='--', lw=1,
                    label=f'% DoS global ({100 * attack_share:.1f}%)')
    axes[0].set(xlabel='% de frames del grupo', xlim=(0, 100),
                title='Composición de clase dentro de cada grupo')
    axes[0].legend(loc='lower right', fontsize=8)

    baseline[['balanced_accuracy', 'macro_f1']].plot.barh(ax=axes[1])
    axes[1].set(xlim=(0, 1), xlabel='métrica', title='Reglas triviales (sin modelo)')
    axes[1].invert_yaxis()
    axes[1].legend(loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=8)
    fig.tight_layout()
    plt.show()
