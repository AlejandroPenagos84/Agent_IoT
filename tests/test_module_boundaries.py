"""Reglas del monolito modular, comprobadas sobre los imports reales."""

import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
STDLIB = sys.stdlib_module_names
# Único archivo de detection autorizado a hablar con auth.
DETECTION_BRIDGE = SRC / 'detection/infrastructure/auth_provider/auth_provider.py'


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def _modules_of(package: str):
    for path in sorted((SRC / package).rglob('*.py')):
        yield path, list(_imports(path))


class ModuleBoundaryTests(unittest.TestCase):
    def test_auth_does_not_know_detection_or_app(self):
        for path, names in _modules_of('auth'):
            bad = [n for n in names if n.split('.')[0] in {'detection', 'app'}]
            self.assertFalse(bad, f'{path.relative_to(SRC)} importa {bad}')

    def test_detection_only_uses_auth_public_api_from_the_bridge(self):
        for path, names in _modules_of('detection'):
            used = [n for n in names if n.split('.')[0] == 'auth']
            if path == DETECTION_BRIDGE:
                self.assertTrue(
                    all(n == 'auth.api' for n in used),
                    f'el puente solo puede usar auth.api: {used}',
                )
            else:
                self.assertFalse(used, f'{path.relative_to(SRC)} importa {used}')

    def test_detection_does_not_know_app(self):
        for path, names in _modules_of('detection'):
            bad = [n for n in names if n.split('.')[0] == 'app']
            self.assertFalse(bad, f'{path.relative_to(SRC)} importa {bad}')

    def test_detection_does_not_know_capture(self):
        for path, names in _modules_of('detection'):
            bad = [n for n in names if n.split('.')[0] == 'capture']
            self.assertFalse(bad, f'{path.relative_to(SRC)} importa {bad}')

    def test_capture_only_uses_itself_wire_and_stdlib(self):
        # La imagen del cliente no instala dependencias de terceros.
        allowed = {'capture', 'wire', '__future__'}
        for path, names in _modules_of('capture'):
            bad = [n for n in names if n.split('.')[0] not in allowed | STDLIB]
            self.assertFalse(bad, f'{path.relative_to(SRC)} importa {bad}')

    def test_wire_is_standalone(self):
        for path, names in _modules_of('wire'):
            bad = [n for n in names if n.split('.')[0] not in STDLIB | {'__future__'}]
            self.assertFalse(bad, f'{path.relative_to(SRC)} importa {bad}')


class WireContractTests(unittest.TestCase):
    def test_feature_order_matches_exported_model(self):
        from wire.protocol import TCP_FEATURE_COLUMNS

        config = json.loads(
            (ROOT / 'modelos_agente_tcp/pipeline_config.json').read_text(encoding='utf-8')
        )
        self.assertEqual(list(TCP_FEATURE_COLUMNS), config['feature_columns_tcp'])

    def test_handshake_round_trip(self):
        from wire.protocol import HELLO, HELLO_ACK, HELLO_ACK_FRAME, hello_frame, message_type

        kind, message = message_type(hello_frame('tok').rstrip(b'\n'))
        self.assertEqual((kind, message['token']), (HELLO, 'tok'))
        self.assertEqual(message_type(HELLO_ACK_FRAME.rstrip(b'\n'))[0], HELLO_ACK)
        self.assertEqual(message_type(b'[1]'), (None, None))


if __name__ == '__main__':
    unittest.main()
