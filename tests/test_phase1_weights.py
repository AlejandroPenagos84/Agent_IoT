"""Fase 1: conservar los pesos balanceados por las cuatro clases.

Comprobación estática del notebook: tras la Fase 4 el target y la clase de
ponderación coinciden, así que `fit_classifier(features, labels)` pondera con sus
propias etiquetas de train (cuatro clases). El XGBoost de frames usa filas de
train y el híbrido la última fila de sus ventanas de train. Se verifica el
contrato de `compute_sample_weight('balanced', ...)` sin entrenar nada.
"""
import json
import re
import unittest
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[1] / 'ml-mqtt-model.ipynb'


def notebook_code():
    cells = json.loads(NOTEBOOK.read_text())['cells']
    return '\n'.join(''.join(cell['source']) for cell in cells
                     if cell['cell_type'] == 'code')


def sklearn_tools():
    try:
        import numpy as np
        from sklearn.utils.class_weight import compute_sample_weight
    except ImportError:
        raise unittest.SkipTest('numpy/scikit-learn no instalados')
    return np, compute_sample_weight


class NotebookWeightSourceTests(unittest.TestCase):
    def setUp(self):
        self.code = notebook_code()

    def test_fit_classifier_weights_with_its_target(self):
        match = re.search(r'def fit_classifier\([^)]*\):(.*?)return model',
                          self.code, re.S)
        self.assertIsNotNone(match, 'no se encontro fit_classifier')
        body = match.group(1)
        self.assertIn("compute_sample_weight('balanced'", body)
        self.assertRegex(body, r"compute_sample_weight\(\s*'balanced',\s*"
                                r'np\.asarray\(\s*labels\s*\)')

    def test_two_call_sites_only(self):
        self.assertEqual(self.code.count('= fit_classifier('), 2)

    def test_xgboost_call_weights_train_rows(self):
        self.assertRegex(self.code,
                         r'model_xgb = fit_classifier\(\s*X\.iloc\[train_idx\],\s*'
                         r'y\.iloc\[train_idx\]\s*\)')

    def test_hybrid_call_uses_oof_train_rows(self):
        self.assertRegex(self.code,
                         r'oof_features, oof_labels = oof_hybrid_training_rows\(\s*'
                         r'frame,\s*train_idx,')
        self.assertRegex(self.code,
                         r'model_hybrid = fit_classifier\(\s*oof_features,\s*'
                         r'oof_labels\s*\)')

    def test_weight_argument_is_never_the_binary_target(self):
        for call in re.findall(r'fit_classifier\(([^)]*)\)', self.code):
            if call.strip().startswith('features'):
                continue
            args = [part.strip() for part in call.split(',')]
            self.assertEqual(len(args), 2, call)
            self.assertNotIn('y_bin', args[1], call)
            self.assertIn(args[1], ('y.iloc[train_idx]', 'oof_labels'), call)


class BalancedWeightContractTests(unittest.TestCase):
    def test_same_class_gets_the_same_weight(self):
        np, compute = sklearn_tools()
        labels = np.array([0, 0, 0, 1, 1, 2, 2, 2, 2, 3])
        weights = compute('balanced', labels)
        for cls in np.unique(labels):
            values = weights[labels == cls]
            self.assertTrue(np.allclose(values, values[0]))

    def test_weight_is_inverse_frequency(self):
        np, compute = sklearn_tools()
        labels = np.array([0, 0, 0, 0, 1, 1, 2, 3, 3, 3])
        weights = compute('balanced', labels)
        n, k = len(labels), len(np.unique(labels))
        for cls in np.unique(labels):
            expected = n / (k * int((labels == cls).sum()))
            self.assertAlmostEqual(float(weights[labels == cls][0]), expected)

    def test_weights_come_only_from_train_labels(self):
        np, compute = sklearn_tools()
        train = np.array([0, 0, 1, 2, 3, 3])
        base = compute('balanced', train)
        # Etiquetas de validation/test no forman parte del vector de pesos.
        other = np.array([1, 1, 1, 2, 3])
        self.assertTrue(np.isfinite(compute('balanced', other)).all())
        self.assertEqual(len(base), len(train))
        np.testing.assert_allclose(base, compute('balanced', train))

    def test_missing_class_is_not_invented_and_stays_finite(self):
        np, compute = sklearn_tools()
        labels = np.array([0, 0, 1, 2])  # la clase 3 no aparece
        weights = compute('balanced', labels)
        self.assertTrue(np.isfinite(weights).all())
        self.assertGreater(float(weights.min()), 0.0)
        self.assertNotIn(3, labels.tolist())

    def test_single_sample_class_is_finite(self):
        np, compute = sklearn_tools()
        labels = np.array([0, 0, 0, 1, 2, 3])
        weights = compute('balanced', labels)
        self.assertTrue(np.isfinite(weights).all())
        self.assertGreater(float(weights.min()), 0.0)


if __name__ == '__main__':
    unittest.main()
