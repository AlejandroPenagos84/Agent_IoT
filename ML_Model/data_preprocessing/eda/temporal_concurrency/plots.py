"""Gráfica de la concurrencia temporal normal/ataque."""

from ..common import NORMAL_LABEL, TARGET_COL, attack_label, get_plt
from .analysis import _capture_frames, attack_window


def plot_temporal_concurrency(df, capture='DoS'):
    """Puntos por frame y frames/s apilados, con todos los frames y solo 1883/8883."""
    import numpy as np
    import pandas as pd

    plt = get_plt()
    attack_name = attack_label(df)
    frames, _, mqtt = _capture_frames(df, capture)
    start, end = attack_window(df, capture)
    duration = end - start
    views = [(frames, 'todos los frames'), (frames[mqtt], 'solo puerto 1883/8883')]
    styles = [(NORMAL_LABEL, 'tab:blue', 0.0), (attack_name, 'tab:red', 1.0)]

    fig, axes = plt.subplots(2, 2, figsize=(16, 8), sharex='col')
    for column, (view, title) in enumerate(views):
        if view.empty:
            axes[0, column].set_title(f'{title}: sin frames')
            axes[1, column].set_title(f'{title}: sin frames')
            continue
        relative = pd.to_numeric(view['frame.time_epoch'], errors='coerce') - start
        for label, color, offset in styles:
            selected = view[TARGET_COL].eq(label)
            axes[0, column].scatter(relative[selected], np.full(int(selected.sum()), offset),
                                    s=2, alpha=0.25, color=color, label=label)
        for axis in axes[:, column]:
            axis.axvline(0, color='black', linestyle='--', linewidth=1)
            axis.axvline(duration, color='black', linestyle='--', linewidth=1)
        axes[0, column].set_yticks([0, 1], [NORMAL_LABEL, attack_name])
        axes[0, column].set(title=f'Puntos por frame ({title})',
                            xlabel=f'segundos desde el primer {attack_name}')
        axes[0, column].legend(markerscale=3, fontsize=8)

        second = np.floor(relative).astype(int)
        counts = pd.crosstab(second, view[TARGET_COL]).reindex(
            range(int(second.min()), int(second.max()) + 1), fill_value=0)
        bottom = 0
        for label, color, _ in styles:
            values = counts[label] if label in counts else 0
            axes[1, column].bar(counts.index, values, bottom=bottom, width=1.0,
                                color=color, label=label)
            bottom = bottom + values
        axes[1, column].set(title=f'Frames por segundo ({title})', ylabel='frames/s',
                            xlabel=f'segundos desde el primer {attack_name}')
        axes[1, column].legend(fontsize=8)
    fig.tight_layout()
    plt.show()
