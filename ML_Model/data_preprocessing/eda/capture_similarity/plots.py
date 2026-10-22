"""Gráfica de la comparación del normal entre capturas."""

from ..common import get_plt, normal_frames
from .analysis import normal_numeric


def plot_capture_similarity(df, origin_bacc, origin_cm):
    """ECDF de ``frame.len`` y ``frame.time_delta`` del normal y matriz del clasificador."""
    import numpy as np

    plt = get_plt()
    source = normal_frames(df)['_capture']
    numeric = normal_numeric(df)
    sources = sorted(source.unique())

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.5))
    for name in sources:
        for ax, column, transform in [(axes[0], 'frame.len', np.asarray),
                                      (axes[1], 'frame.time_delta',
                                       lambda v: np.log10(v + 1e-6))]:
            values = np.sort(transform(numeric.loc[source.eq(name), column].dropna().to_numpy()))
            ax.plot(values, np.arange(1, len(values) + 1) / len(values), label=name)
    axes[0].set(xlabel='frame.len (bytes)', ylabel='proporción acumulada',
                title='ECDF frame.len (normal)')
    axes[1].set(xlabel='log10(frame.time_delta + 1e-6)', title='ECDF frame.time_delta (normal)')
    for ax in axes[:2]:
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)

    matrix = origin_cm.to_numpy()
    image = axes[2].imshow(matrix, cmap='Blues', vmin=0, vmax=1)
    axes[2].set_xticks(range(len(sources)), sources)
    axes[2].set_yticks(range(len(sources)), sources)
    for (i, j), value in np.ndenumerate(matrix):
        axes[2].text(j, i, f'{value:.2f}', ha='center', va='center',
                     color='white' if value > 0.6 else 'black')
    axes[2].set(xlabel='captura predicha', ylabel='captura real',
                title=f'Clasificador de origen (bacc={origin_bacc:.2f}, '
                      f'azar={1 / len(sources):.2f})')
    fig.colorbar(image, ax=axes[2])
    fig.tight_layout()
    plt.show()
