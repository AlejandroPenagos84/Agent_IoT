"""Métricas binarias (1 = DoS) y falsos positivos por captura de origen."""

BASE_METRICS = ['macro_f1', 'balanced_accuracy', 'roc_auc',
                'dos_recall', 'dos_precision', 'normal_recall']


def classification_metrics(labels, prediction, probability=None):
    from sklearn.metrics import (balanced_accuracy_score, f1_score, precision_score,
                                 recall_score, roc_auc_score)

    result = {
        'macro_f1': float(f1_score(labels, prediction, average='macro', zero_division=0)),
        'balanced_accuracy': float(balanced_accuracy_score(labels, prediction)),
        'dos_recall': float(recall_score(labels, prediction, pos_label=1, zero_division=0)),
        'dos_precision': float(precision_score(labels, prediction, pos_label=1,
                                               zero_division=0)),
        'normal_recall': float(recall_score(labels, prediction, pos_label=0, zero_division=0)),
    }
    if probability is not None:
        result['roc_auc'] = float(roc_auc_score(labels, probability))
    return result


def false_positive_by_capture(labels, prediction, captures):
    """``fp_<captura>``: fracción del normal de cada captura predicho como DoS."""
    import numpy as np

    normal = labels == 0
    return {f'fp_{c}': float(prediction[normal & (captures == c)].mean())
            for c in sorted(set(captures[normal]))} or {'fp': np.nan}


def metric_columns(folds):
    """Métricas base más las columnas ``fp_*`` presentes, en orden estable."""
    return [c for c in BASE_METRICS if c in folds] + sorted(
        c for c in folds.columns if c.startswith('fp_'))
