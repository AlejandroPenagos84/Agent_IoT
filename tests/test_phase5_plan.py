"""Fase 5: comprobaciones estáticas del notebook y del orquestador final.

No ejecuta el notebook ni el orquestador. Verifica el contrato multiclase, la
campaña de evaluación escrita y que el procedimiento final existe con sus
argumentos obligatorios.
"""
import ast
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

try:
    import validate_notebook
except ImportError:  # pragma: no cover - descubrimiento alternativo
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'validate_notebook', TESTS / 'validate_notebook.py')
    validate_notebook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validate_notebook)


class NotebookPhase5Tests(unittest.TestCase):
    def test_static_contract(self):
        self.assertTrue(validate_notebook.validate())

    def test_notebook_parses(self):
        notebook = validate_notebook.notebook_json()
        for index, cell in enumerate(notebook['cells']):
            if cell['cell_type'] == 'code':
                ast.parse(''.join(cell['source']))
        self.assertGreater(len(notebook['cells']), 20)


class FinalProcedureTests(unittest.TestCase):
    def setUp(self):
        self.source = (TESTS / 'run_final_validation.py').read_text()

    def test_parses(self):
        ast.parse(self.source)

    def test_required_arguments(self):
        self.assertIn("'--data-dir'", self.source)
        self.assertIn("'--output-dir'", self.source)
        self.assertIn('required=True', self.source)

    def test_rejects_existing_output(self):
        self.assertIn('El directorio de salida ya existe', self.source)

    def test_checks_parity_and_report(self):
        self.assertIn('def check_parity(', self.source)
        self.assertIn('validation_report.json', self.source)

    def test_does_not_copy_artifacts(self):
        self.assertNotIn('shutil.copy', self.source)
        self.assertNotIn('modelos_agente/\' ', self.source)


if __name__ == '__main__':
    unittest.main()
