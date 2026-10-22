"""Gráficas de resultados de la evaluación (import lazy de matplotlib)."""

SET_COLORS = {'A': '#c0392b', 'B': '#4e79a7'}


def _plt():
    import matplotlib.pyplot as plt
    return plt


def _color(name, index):
    return SET_COLORS.get(name, f'C{index}')


def plot_fold_metrics(folds, baseline_f1=None, metrics=('macro_f1', 'balanced_accuracy',
                                                         'dos_recall', 'normal_recall')):
    """Media ± std por set para cada métrica, con puntos por fold."""
    import numpy as np

    plt = _plt()
    sets = list(dict.fromkeys(folds['set']))
    fig, ax = plt.subplots(figsize=(10, 4))
    width = 0.8 / len(sets)
    x = np.arange(len(metrics))
    for i, name in enumerate(sets):
        part = folds[folds['set'].eq(name)]
        offset = x + (i - (len(sets) - 1) / 2) * width
        ax.bar(offset, part[list(metrics)].mean(), width, yerr=part[list(metrics)].std(),
               color=_color(name, i), alpha=0.8, label=name, capsize=3)
        for j, metric in enumerate(metrics):
            ax.scatter(np.full(len(part), offset[j]), part[metric], s=10, color='black',
                       zorder=3)
    if baseline_f1 is not None:
        ax.axhline(baseline_f1, color='gray', ls='--', lw=1,
                   label=f'línea base macro-F1 ({baseline_f1:.3f})')
    low = min(folds[list(metrics)].min().min(), baseline_f1 or 1)
    ax.set(xticks=x, xticklabels=metrics, ylim=(max(0, low - 0.02), 1.0),
           title='Métricas por set (media ± std; puntos = folds)')
    ax.legend(loc='lower right', fontsize=8)
    fig.tight_layout()
    plt.show()


def plot_fp_by_capture(means):
    """Tasa de falsos positivos por captura de origen del normal."""
    plt = _plt()
    fp = means[[c for c in means.columns if c.startswith('fp_')]]
    fp.columns = [c[3:] for c in fp.columns]
    ax = fp.T.plot.bar(rot=0, figsize=(7, 3.5),
                       color=[_color(n, i) for i, n in enumerate(fp.index)])
    ax.set(ylabel='FP (normal predicho DoS)', xlabel='captura de origen del normal',
           title='Falsos positivos por captura')
    for container in ax.containers:
        ax.bar_label(container, fmt='%.3f', fontsize=7)
    plt.tight_layout()
    plt.show()


def plot_importance(importance, top=10):
    """Importancia media de las ``top`` features de cada set (un panel por set)."""
    plt = _plt()
    sets = list(importance.columns)
    fig, axes = plt.subplots(1, len(sets), figsize=(6 * len(sets), 4), squeeze=False)
    for i, (ax, name) in enumerate(zip(axes[0], sets)):
        values = importance[name].dropna().sort_values(ascending=False).head(top)
        share = values / importance[name].sum()
        share.iloc[::-1].plot.barh(ax=ax, color=_color(name, i))
        ax.set(xlabel='fracción de la importancia total', title=f'Importancia media ({name})')
        for patch, value in zip(ax.patches, share.iloc[::-1]):
            ax.text(patch.get_width(), patch.get_y() + patch.get_height() / 2,
                    f' {value:.1%}', va='center', fontsize=7)
    fig.tight_layout()
    plt.show()


def plot_tls_sensitivity(tls):
    """Macro-F1 por fold antes y después del padding TLS."""
    plt = _plt()
    ax = tls[['macro_f1_base', 'macro_f1_tls']].plot.bar(rot=0, figsize=(7, 3.5))
    low = tls[['macro_f1_base', 'macro_f1_tls']].min().min()
    ax.set(ylim=(max(0, low - 0.01), 1.0), xlabel='fold', ylabel='macro-F1',
           title=f"B con padding TLS 21–40 B (caída media {tls['caida'].mean():.4f})")
    ax.legend(['sin padding', 'con padding'], fontsize=8, loc='lower right')
    plt.tight_layout()
    plt.show()


def plot_scope_vs_full(data, metric='macro_f1'):
    """``data``: filas = vistas, columnas = sets, valores = ``metric``."""
    plt = _plt()
    ax = data.plot.bar(rot=0, figsize=(6, 3.5),
                       color=[_color(n, i) for i, n in enumerate(data.columns)])
    low = data.min().min()
    ax.set(ylim=(max(0, low - 0.01), 1.0), ylabel=metric,
           title=f'{metric}: vista mqtt vs todo el tráfico')
    for container in ax.containers:
        ax.bar_label(container, fmt='%.4f', fontsize=7)
    plt.tight_layout()
    plt.show()


def plot_confusion(share, counts, title='Matriz de confusión OOF'):
    """Heatmap del % por fila real, anotado con conteos."""
    import numpy as np

    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.5, 3.8))
    image = ax.imshow(share.to_numpy(), cmap='Blues', vmin=0, vmax=100)
    ax.set_xticks(range(share.shape[1]), share.columns)
    ax.set_yticks(range(share.shape[0]), share.index)
    for (i, j), value in np.ndenumerate(share.to_numpy()):
        ax.text(j, i, f'{value:.2f}%\n({counts.iat[i, j]:,})', ha='center', va='center',
                color='white' if value > 60 else 'black', fontsize=9)
    ax.set_title(title)
    fig.colorbar(image, ax=ax, fraction=0.046)
    fig.tight_layout()
    plt.show()


def plot_ablation(views, metric='macro_f1'):
    """``views``: ``{vista: medias por set}``. Barras de ``metric`` por set y vista."""
    import pandas as pd

    plt = _plt()
    data = pd.DataFrame({name: means[metric] for name, means in views.items()})
    ax = data.plot.barh(figsize=(9, 0.6 * len(data) + 1.5))
    low = data.min().min()
    ax.set(xlim=(max(0, low - 0.01), 1.0), xlabel=metric, title=f'Ablaciones de B ({metric})')
    ax.invert_yaxis()
    for container in ax.containers:
        ax.bar_label(container, fmt='%.4f', fontsize=7)
    ax.legend(fontsize=8, loc='lower right')
    plt.tight_layout()
    plt.show()


def plot_univariate_auc(table):
    """AUC univariada por feature en cada vista (0,5 = no separa)."""
    plt = _plt()
    data = table[[c for c in table.columns if c.startswith('AUC ')]]
    data.columns = [c[4:] for c in data.columns]
    ax = data.iloc[::-1].plot.barh(figsize=(8, 0.4 * len(data) + 1.5))
    ax.axvline(0.5, color='gray', ls='--', lw=1)
    ax.set(xlim=(0.45, 1.0), xlabel='AUC univariada (mejor dirección)',
           title='Separación de cada feature por sí sola')
    ax.legend(fontsize=8, loc='lower right')
    plt.tight_layout()
    plt.show()
