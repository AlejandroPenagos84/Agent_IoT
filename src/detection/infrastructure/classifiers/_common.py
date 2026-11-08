from __future__ import annotations

import json
import os


def load_config(model_dir: str) -> dict:
    """Load the exported pipeline contract from a model directory."""
    with open(os.path.join(model_dir, 'pipeline_config.json')) as handle:
        return json.load(handle)


def validate_named_features(expected, actual, where: str) -> None:
    """Ensure an exported model exposes exactly the configured feature names."""
    if actual is None:
        raise ValueError(
            f'{where}: el artefacto no expone nombres de features; '
            'no se puede verificar contra pipeline_config.json')
    expected = list(expected)
    actual = list(actual)
    if expected != actual:
        raise ValueError(
            f'{where}: las features de pipeline_config.json no coinciden con '
            f'el modelo exportado.\n'
            f'  config ({len(expected)}): {expected}\n'
            f'  modelo ({len(actual)}): {actual}\n'
            'Reentrena y reexporta modelos_agente_tcp/ desde 03_modelo_tcp.ipynb.')
    return None
