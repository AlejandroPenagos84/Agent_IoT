"""Gráficas de la regla STRUCTURAL_NULL: heatmap (paso 1) y scatter (paso 2)."""

from ..common import NO_MQTT, get_plt, packet_types


def plot_structural_presence(df, columns):
    """Heatmap: % de frames de cada tipo de paquete en los que la columna tiene valor."""
    plt = get_plt()
    import pandas as pd

    types = packet_types(df)
    presence = pd.DataFrame({c: df[c].notna() for c in columns})
    share = (100 * presence.groupby(types).mean()).T
    share = share[[c for c in share.columns if c != NO_MQTT] + [NO_MQTT]]
    fig, ax = plt.subplots(figsize=(1 + 0.75 * share.shape[1], 0.4 * len(columns) + 1.5))
    image = ax.imshow(share.to_numpy(), aspect='auto', cmap='Blues', vmin=0, vmax=100)
    ax.set_xticks(range(share.shape[1]), share.columns, rotation=45, ha='right')
    ax.set_yticks(range(len(columns)), share.index)
    for (i, j), value in pd.DataFrame(share.to_numpy()).stack().items():
        if value > 0:
            ax.text(j, i, f'{value:.0f}', ha='center', va='center', fontsize=7,
                    color='white' if value > 60 else 'black')
    fig.colorbar(image, ax=ax, label='% de frames del tipo con valor')
    ax.set_title('¿En qué tipo de paquete existe cada columna parcialmente nula?')
    fig.tight_layout()
    plt.show()


def plot_packet_separation(separation):
    """Paso 2 en gráfica: proporción de cada tipo en normal vs DoS (log-log)."""
    plt = get_plt()

    data = separation.replace(0, 1e-4)
    fig, ax = plt.subplots(figsize=(7, 6))
    colors = ['#c0392b' if s else '#7f8c8d' for s in separation['separates']]
    ax.scatter(data['pct_normal'], data['pct_attack'], c=colors, s=40)
    for name, row in data.iterrows():
        ax.annotate(name, (row['pct_normal'], row['pct_attack']), fontsize=8,
                    xytext=(4, 2), textcoords='offset points')
    low, high = 1e-4, 100
    ax.plot([low, high], [low, high], '--', color='grey', lw=1)
    ax.set(xscale='log', yscale='log', xlim=(low / 2, high * 2), ylim=(low / 2, high * 2),
           xlabel='% de frames normal', ylabel='% de frames DoS',
           title='Tipos de paquete: rojo = separa DoS (0% se dibuja en 1e-4)')
    fig.tight_layout()
    plt.show()
