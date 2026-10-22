"""Criterio de decisión A vs B y leave-one-capture-out del normal."""

from .models import fit_balanced

MAX_F1_GAP = 0.03
DOMINANT_SHARE = 0.50


def decide_a_vs_b(means, baseline_f1, importance_b, max_gap=MAX_F1_GAP):
    """Evalúa el criterio del plan y devuelve ``(tabla de checks, decisión)``.

    B se elige si su macro-F1 queda a ≤ ``max_gap`` de A, supera la línea base y
    no aumenta los FP en ninguna captura de origen.
    """
    import pandas as pd

    a, b = means.loc['A'], means.loc['B']
    fp = [c for c in means.columns if c.startswith('fp_')]
    worse_fp = [c for c in fp if b[c] > a[c] + 1e-12]
    share = float(importance_b.max() / importance_b.sum())
    checks = pd.DataFrame([
        {'criterio': f'macro-F1 de B a ≤ {max_gap} de A',
         'valor': f"A-B = {a['macro_f1'] - b['macro_f1']:+.4f}",
         'cumple': bool(a['macro_f1'] - b['macro_f1'] <= max_gap)},
        {'criterio': 'B supera la línea base',
         'valor': f"{b['macro_f1']:.4f} vs {baseline_f1:.4f}",
         'cumple': bool(b['macro_f1'] >= baseline_f1)},
        {'criterio': 'B no aumenta FP en ninguna captura',
         'valor': ', '.join(worse_fp) or 'ninguna empeora',
         'cumple': not worse_fp},
        {'criterio': f'ninguna feature de B pesa > {DOMINANT_SHARE:.0%} (aviso, no bloquea)',
         'valor': f'{importance_b.idxmax()} = {share:.1%}',
         'cumple': share <= DOMINANT_SHARE},
    ]).set_index('criterio')
    decision = 'B' if checks['cumple'].iloc[:3].all() else 'A'
    return checks, decision


def leave_one_capture_out(feature_sets, labels, captures, seed=42):
    """Entrena sin el normal de una captura y mide el FP sobre ese normal."""
    import numpy as np
    import pandas as pd

    rows = []
    for held_out in sorted(set(captures[labels == 0])):
        test = (labels == 0) & (captures == held_out)
        train_idx, test_idx = np.where(~test)[0], np.where(test)[0]
        for name, features in feature_sets.items():
            model = fit_balanced(features.iloc[train_idx], labels[train_idx], seed)
            prediction = model.predict(features.iloc[test_idx])
            rows.append({'set': name, 'captura_held_out': held_out,
                         'normal_recall': float((prediction == 0).mean()),
                         'fp_rate': float((prediction == 1).mean()),
                         'samples': int(len(test_idx))})
    return pd.DataFrame(rows)
