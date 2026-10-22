"""Exportación y validación del modelo final B (XGBoost solo TCP).

Escribe en ``modelos_agente_tcp/``:

- ``xgb_tcp.ubj``: booster con nombres de features en el orden de entrenamiento.
- ``le_target.joblib``: ``LabelEncoder`` con ``classes_ = ['normal', 'ataque']``
  (0 = normal). Solo se usa ``inverse_transform``; ``transform`` asume orden
  alfabético y no debe usarse con este encoder.
- ``pipeline_config.json``, ``metrics.json``, ``evaluation_split.json`` y
  ``manifest.json``.

El agente actual no carga este formato (espera artefactos MQTT); integrar el
modelo exige el builder incremental TCP y un adaptador ``TcpXgbClassifier``.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

CLASS_NAMES = ['normal', 'ataque']
MODEL_FILE = 'xgb_tcp.ubj'
ARTIFACT_FILES = [MODEL_FILE, 'le_target.joblib', 'pipeline_config.json', 'metrics.json',
                  'evaluation_split.json']


def _sha256(path):
    from data_preprocessing.artifacts import sha256_file
    return sha256_file(path)


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n',
                          encoding='utf-8')


def _to_builtin(value):
    """Convierte numpy/pandas a tipos JSON."""
    import numpy as np
    import pandas as pd

    if isinstance(value, pd.DataFrame):
        return {str(k): _to_builtin(v) for k, v in value.to_dict(orient='index').items()}
    if isinstance(value, pd.Series):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def build_pipeline_config(feature_columns, xgb_params, seed, n_splits, window_seconds,
                          training_scope):
    """Contrato que necesita el agente para reconstruir y aplicar el modelo."""
    return {
        'dataset': 'MQTT_UAD/DoS.csv',
        'task': 'dos_binary',
        'positive_class': 'DoS',
        'feature_mode': 'tcp',
        'feature_columns_tcp': list(feature_columns),
        'class_names': CLASS_NAMES,
        'normal_idx': 0,
        'model_file': MODEL_FILE,
        'window_size': 11,
        'seq_len': 10,
        # build_tcp_features rellena con 0 (sin historial en la ventana causal).
        'nan_fill': 0.0,
        'tcp_window_seconds': window_seconds,
        'tcp_window_causal': True,
        'mqtt_ports': [1883, 8883],
        'split_strategy': 'grouped_by_connection',
        'cv_folds': n_splits,
        'seed': seed,
        'hyperparameters': dict(xgb_params),
        # El modelo solo es válido para frames con puerto 1883/8883 en origen o destino;
        # las ventanas TCP se calculan solo con esos frames.
        'training_scope': training_scope,
        'classify_only_mqtt_ports': training_scope == 'mqtt_ports',
        'trained_on': ('frames con puerto 1883/8883 de DoS.csv + normal de MitM.csv e '
                       'Intrusion.csv' if training_scope == 'mqtt_ports'
                       else 'df_raw completo (DoS.csv + normal de MitM.csv e Intrusion.csv)'),
    }


def evaluation_split(df, splits, seed):
    """Fold de test de cada fila, identificada por ``(_capture, _original_row)``."""
    import numpy as np

    fold_of = np.full(len(df), -1, dtype=int)
    for fold, (_, test) in enumerate(splits):
        fold_of[test] = fold
    captures = df['_capture'].to_numpy()
    rows = df['_original_row'].to_numpy()
    return {
        'seed': seed,
        'selection': 'filas del DataFrame de entrenamiento (df_raw del notebook 01, '
                     'filtrado por puerto 1883/8883 si training_scope = mqtt_ports)',
        'group_key': '_connection',
        'row_key': ['_capture', '_original_row'],
        'n_splits': len(splits),
        'test_fold_by_capture': {
            str(capture): {'original_row': rows[captures == capture].astype(int).tolist(),
                           'test_fold': fold_of[captures == capture].tolist()}
            for capture in sorted(set(captures))
        },
    }


def export_tcp_model(model, out_dir, *, df, features, splits, metrics, source_manifest,
                     seed, window_seconds, training_scope='mqtt_ports', version='tcp-B-v2'):
    """Escribe los seis artefactos y devuelve el manifiesto."""
    import joblib
    import numpy as np
    from sklearn.preprocessing import LabelEncoder

    from evaluation.models import XGB_PARAMS

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    booster_names = model.get_booster().feature_names
    if list(booster_names) != list(features.columns):
        raise ValueError(f'Orden de features del modelo {booster_names} != {list(features.columns)}')

    model.save_model(out_dir / MODEL_FILE)
    encoder = LabelEncoder()
    encoder.classes_ = np.array(CLASS_NAMES, dtype=object)
    joblib.dump(encoder, out_dir / 'le_target.joblib')
    _write_json(out_dir / 'pipeline_config.json', build_pipeline_config(
        features.columns, XGB_PARAMS, seed, len(splits), window_seconds, training_scope))
    _write_json(out_dir / 'metrics.json', _to_builtin(metrics))
    _write_json(out_dir / 'evaluation_split.json', evaluation_split(df, splits, seed))

    labels = df['type']
    manifest = {
        'version': version,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'generated_by': 'ML_Model/03_modelo_tcp.ipynb',
        'seed': seed,
        'training_scope': training_scope,
        'source_artifact': {'path': source_manifest['artifact'],
                            'sha256': source_manifest['df_raw_sha256']},
        'feature_columns': list(features.columns),
        'n_features': int(features.shape[1]),
        'training_rows': int(len(df)),
        'counts_by_class': {k: int(v) for k, v in labels.value_counts().items()},
        'counts_by_capture_and_class': {
            str(c): {str(k): int(v) for k, v in part.value_counts().items()}
            for c, part in labels.groupby(df['_capture'])},
        'files': {name: _sha256(out_dir / name) for name in ARTIFACT_FILES},
    }
    _write_json(out_dir / 'manifest.json', manifest)
    return manifest


def validate_export(out_dir, model, sample, expected_columns):
    """Recarga los artefactos y compara con el modelo en memoria sobre ``sample``.

    Devuelve ``(tabla de checks, todo_ok)``.
    """
    import joblib
    import numpy as np
    import pandas as pd
    from xgboost import XGBClassifier

    out_dir = Path(out_dir)
    config = json.loads((out_dir / 'pipeline_config.json').read_text(encoding='utf-8'))
    manifest = json.loads((out_dir / 'manifest.json').read_text(encoding='utf-8'))
    encoder = joblib.load(out_dir / 'le_target.joblib')
    loaded = XGBClassifier()
    loaded.load_model(out_dir / config['model_file'])

    ordered = sample[config['feature_columns_tcp']]
    memory_proba = model.predict_proba(sample)[:, 1]
    loaded_proba = loaded.predict_proba(ordered)[:, 1]
    labels = encoder.inverse_transform(loaded.predict(ordered))
    hashes_ok = all(_sha256(out_dir / name) == digest
                    for name, digest in manifest['files'].items())
    checks = pd.DataFrame([
        {'check': 'archivos presentes',
         'ok': all((out_dir / f).is_file() for f in [*ARTIFACT_FILES, 'manifest.json'])},
        {'check': 'hashes del manifiesto', 'ok': hashes_ok},
        {'check': 'columnas = TCP_FEATURE_COLUMNS',
         'ok': config['feature_columns_tcp'] == list(expected_columns)},
        {'check': 'nombres del booster = columnas',
         'ok': list(loaded.get_booster().feature_names) == list(expected_columns)},
        {'check': 'class_names y normal_idx',
         'ok': list(encoder.classes_) == CLASS_NAMES and config['normal_idx'] == 0},
        {'check': f'probabilidades idénticas ({len(sample):,} frames)',
         'ok': bool(np.allclose(memory_proba, loaded_proba, atol=1e-6))},
        {'check': 'etiquetas en class_names', 'ok': set(labels) <= set(CLASS_NAMES)},
        {'check': 'sin features mqtt.*',
         'ok': not any(c.startswith('mqtt.') for c in config['feature_columns_tcp'])},
    ]).set_index('check')
    return checks, bool(checks['ok'].all())
