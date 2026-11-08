"""Artefacto limpio ``df_raw`` y su manifiesto.

``01_eda_politica.ipynb`` lo guarda con ``save_clean_artifact``; los notebooks 02
y 03 lo leen con ``load_clean_artifact``, que verifica el hash del manifiesto. Se
usa joblib (no Parquet) porque conserva los tuples de ``_connection`` y
``_direction``.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .feature_engineering import INTERNAL_COLUMNS
from .load_data import TARGET_COL

LABELS = ['normal', 'DoS']
TUPLE_KEYS = ['_connection', '_direction']
# Identidad y reloj de captura: nunca deben sobrevivir a la política.
FORBIDDEN_COLUMNS = ['ip.src', 'ip.dst', 'eth.src', 'eth.dst', 'mqtt.clientid',
                     'frame.time_relative', 'frame.number']
# Se conservan solo como contexto (orden de ventanas y banderas de puerto).
CONTEXT_ONLY_COLUMNS = ['frame.time_epoch', 'tcp.srcport', 'tcp.dstport']


def sha256_file(path, chunk=1 << 20):
    """Hash SHA-256 de un archivo, leído por bloques."""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(chunk), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_clean_frame(df, captures):
    """Falla si ``df`` no cumple el contrato del artefacto limpio."""
    if df.empty:
        raise ValueError('df_raw está vacío')
    labels = set(df[TARGET_COL].unique())
    if labels != set(LABELS):
        raise ValueError(f'Etiquetas inesperadas: {sorted(labels)}')
    forbidden = set(FORBIDDEN_COLUMNS) & set(df.columns)
    if forbidden:
        raise ValueError(f'Columnas de identidad/reloj en df_raw: {sorted(forbidden)}')
    for key in TUPLE_KEYS:
        if not df[key].map(lambda v: isinstance(v, tuple)).all():
            raise ValueError(f'{key} no contiene tuples')
    unknown = set(df['_capture'].unique()) - set(captures)
    if unknown:
        raise ValueError(f'Capturas desconocidas: {sorted(unknown)}')


def column_roles(df, policy):
    """Rol de cada columna: target, internal_key, context, keep o derive."""
    action = policy.set_index('columna')['acción']
    roles = {}
    for column in df.columns:
        if column == TARGET_COL:
            roles[column] = 'target'
        elif column in INTERNAL_COLUMNS:
            roles[column] = 'internal_key'
        elif column in CONTEXT_ONLY_COLUMNS:
            roles[column] = 'context'
        else:
            roles[column] = action[column].lower()
    return roles


def _counts(table):
    return {str(row): {str(col): int(n) for col, n in values.items()}
            for row, values in table.iterrows()}


def class_counts(df):
    """``(frames por captura y clase, conexiones por captura y clase)``."""
    import pandas as pd

    frames = pd.crosstab(df['_capture'], df[TARGET_COL]).reindex(columns=LABELS, fill_value=0)
    connections = (df.groupby(['_capture', TARGET_COL])['_connection'].nunique()
                   .unstack(fill_value=0).reindex(columns=LABELS, fill_value=0))
    return frames, connections


def build_manifest(df, *, artifact_path, repo_root, files, normal_only, policy,
                   dropped_columns, seed, feature_version, feature_columns, extra=None):
    """Diccionario del manifiesto (rutas relativas a ``repo_root``)."""
    repo_root = Path(repo_root)
    frames, connections = class_counts(df)
    return {
        'artifact': Path(artifact_path).relative_to(repo_root).as_posix(),
        'artifact_version': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'generated_by': 'ML_Model/01_eda_politica.ipynb',
        'seed': seed,
        'feature_version': feature_version,
        'feature_columns': {name: list(cols) for name, cols in feature_columns.items()},
        'captures': {
            name: {'file': Path(path).relative_to(repo_root).as_posix(),
                   'sha256': sha256_file(path),
                   'labels_kept': ['normal'] if name in normal_only else LABELS}
            for name, path in files.items()
        },
        'labels': LABELS,
        'target_column': TARGET_COL,
        'shape': {'rows': int(df.shape[0]), 'columns': int(df.shape[1])},
        'counts_by_class': {k: int(v) for k, v in
                            df[TARGET_COL].value_counts().reindex(LABELS).items()},
        'counts_by_capture_and_class': _counts(frames),
        'connections_by_class': {k: int(v) for k, v in
                                 df.groupby(TARGET_COL)['_connection'].nunique()
                                 .reindex(LABELS).items()},
        'connections_by_capture_and_class': _counts(connections),
        'columns': list(df.columns),
        'column_roles': column_roles(df, policy),
        'dropped_columns': sorted(dropped_columns),
        'policy_summary': {f'{a}/{m}': int(n) for (a, m), n in
                           policy.groupby(['acción', 'motivo']).size().items()},
        **(extra or {}),
        'df_raw_sha256': sha256_file(artifact_path),
    }


def save_clean_artifact(df, artifacts_dir, manifest_kwargs):
    """Valida, guarda ``df_raw.joblib``, lo recarga y escribe ``manifest.json``.

    Devuelve el manifiesto. ``manifest_kwargs`` son los argumentos de
    ``build_manifest`` salvo ``artifact_path``.
    """
    import joblib

    validate_clean_frame(df, manifest_kwargs['files'])
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_dir / 'df_raw.joblib'
    joblib.dump(df, artifact_path)

    reloaded = joblib.load(artifact_path)
    if reloaded.shape != df.shape or list(reloaded.columns) != list(df.columns):
        raise ValueError('El artefacto recargado no coincide con df_raw')
    for column in [TARGET_COL, *TUPLE_KEYS]:
        if not reloaded[column].equals(df[column]):
            raise ValueError(f'{column} cambió al recargar el artefacto')
    del reloaded

    manifest = build_manifest(df, artifact_path=artifact_path, **manifest_kwargs)
    (artifacts_dir / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest


def load_clean_artifact(artifacts_dir, verify_hash=True):
    """``(df_raw, manifest)``; falla si el hash o la forma no coinciden."""
    import joblib

    artifacts_dir = Path(artifacts_dir)
    manifest = json.loads((artifacts_dir / 'manifest.json').read_text(encoding='utf-8'))
    artifact_path = artifacts_dir / 'df_raw.joblib'
    if verify_hash and sha256_file(artifact_path) != manifest['df_raw_sha256']:
        raise ValueError('df_raw.joblib no coincide con el hash del manifiesto; '
                         'reejecuta 01_eda_politica.ipynb')
    df = joblib.load(artifact_path)
    if list(df.columns) != manifest['columns'] or len(df) != manifest['shape']['rows']:
        raise ValueError('df_raw.joblib no coincide con el manifiesto')
    return df, manifest
