"""Procedimiento final de validación de la Fase 5.

Lo ejecuta **el usuario**; el agente no lo ejecuta. Orquesta, en este orden:

1. Comprobar dependencias y los CSV de `--data-dir`.
2. Validar estáticamente el notebook.
3. Compilar y ejecutar `unittest`; detenerse si algo falla.
4. Ejecutar el notebook con rutas locales (copia temporal, sin mutar el original).
5. Comprobar paridad del paquete candidato con los adapters (TCP y L2).
6. Escribir un informe con cobertura, métricas y manifiesto.

Ejemplo:

    python tests/run_final_validation.py --data-dir /RUTA/A/CSV \
        --output-dir /RUTA/NUEVA/validacion-final
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REQUIRED_FILES = ('DoS.csv', 'MitM.csv', 'Intrusion.csv')
KAGGLE_PREFIX = '/kaggle/input/datasets/alejandropenagos79/dataset'
KAGGLE_EXPORT = "'/kaggle/working/modelos_agente'"
KAGGLE_ZIP = "'/kaggle/working/modelos_agente.zip'"

DEPENDENCIES = ('numpy', 'pandas', 'sklearn', 'joblib', 'torch', 'xgboost',
                'nbformat')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', required=True,
                        help='Directorio con DoS.csv, MitM.csv e Intrusion.csv')
    parser.add_argument('--output-dir', required=True,
                        help='Directorio NUEVO para la salida; no debe existir')
    parser.add_argument('--skip-ablation', action='store_true',
                        help='No ejecutar las ablations A/B/C de 5.5')
    parser.add_argument('--skip-temporal', action='store_true',
                        help='No ejecutar el split temporal de 5.4')
    return parser.parse_args(argv)


def check_dependencies():
    missing = []
    for module in DEPENDENCIES:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise SystemExit('Faltan dependencias: ' + ', '.join(missing))
    try:
        import nbclient  # noqa: F401
        return 'nbclient'
    except ImportError:
        try:
            import nbconvert  # noqa: F401
            return 'nbconvert'
        except ImportError:
            raise SystemExit('Falta nbclient o nbconvert para ejecutar el notebook')


def check_data(data_dir):
    paths = {}
    for name in REQUIRED_FILES:
        path = data_dir / name
        if not path.is_file():
            raise SystemExit('Falta el CSV requerido: ' + str(path))
        paths[name] = path
    return paths


def run_command(command, cwd):
    print('$', ' '.join(str(part) for part in command))
    completed = subprocess.run([str(part) for part in command], cwd=str(cwd),
                               text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    if completed.returncode:
        raise SystemExit('Fallo el comando: ' + ' '.join(str(p) for p in command))
    return completed


def check_dependencies_and_data(data_dir):
    check_dependencies()
    check_data(data_dir)


def static_validation(root):
    run_command([sys.executable, str(root / 'tests' / 'validate_notebook.py')], root)


def compile_and_test(root):
    run_command([sys.executable, '-m', 'compileall', '-q',
                 str(root / 'domain'), str(root / 'application'),
                 str(root / 'infrastructure'), str(root / 'composition_root.py')], root)
    run_command([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], root)


def prepare_notebook(root, data_dir, output_dir, skip_ablation, skip_temporal):
    notebook = json.loads((root / 'ml-mqtt-model.ipynb').read_text())
    export_dir = output_dir / 'modelos_agente'
    for cell in notebook['cells']:
        if cell['cell_type'] != 'code':
            continue
        source = ''.join(cell['source'])
        for name in ('DoS', 'MitM', 'Intrusion'):
            source = source.replace('{0}/{1}.csv'.format(KAGGLE_PREFIX, name),
                                    str(data_dir / '{0}.csv'.format(name)))
        source = source.replace(KAGGLE_EXPORT, repr(str(export_dir)))
        source = source.replace(KAGGLE_ZIP, repr(str(output_dir / 'modelos_agente.zip')))
        if skip_ablation:
            source = source.replace('EVAL_ABLATIONS = True', 'EVAL_ABLATIONS = False')
        if skip_temporal:
            source = source.replace('EVAL_TEMPORAL = True', 'EVAL_TEMPORAL = False')
        cell['source'] = source.splitlines(keepends=True)
    return notebook


def execute_notebook(notebook, output_dir, root):
    import nbformat
    node = nbformat.from_dict(notebook)
    executed_path = output_dir / 'ml-mqtt-model-executed.ipynb'
    try:
        from nbclient import NotebookClient
        client = NotebookClient(node, timeout=7200, kernel_name='python3',
                                resources={'metadata': {'path': str(root)}})
        client.execute()
    except ImportError:
        temporary = output_dir / 'ml-mqtt-model-prepared.ipynb'
        nbformat.write(node, str(temporary))
        run_command([sys.executable, '-m', 'nbconvert', '--to', 'notebook',
                     '--execute', '--ExecutePreprocessor.timeout=7200',
                     '--output', str(executed_path), str(temporary)], root)
        return executed_path
    nbformat.write(node, str(executed_path))
    return executed_path


def check_parity(export_dir, root):
    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(root))
    from application.ports.ports_out import FeatureSource
    from application.ports.types import Frame
    from infrastructure.classifiers import (HybridClassifier, LstmClassifier,
                                            XgbClassifier)
    from infrastructure.classifiers import _common
    from infrastructure.features import ContextFeatureSource
    from infrastructure.tshark.tshark_feature_source import TsharkFeatureSource

    samples = json.loads((export_dir / 'parity_samples.json').read_text())
    config = _common.load_config(str(export_dir))
    known_origins = _common.load_known_origins(str(export_dir), config)
    known_topics = _common.load_known_topics(str(export_dir), config)
    statistics = _common.load_nan_statistics(str(export_dir), config)
    import joblib
    scaler = joblib.load(str(export_dir / 'scaler.joblib'))
    report = {}

    class Replay(FeatureSource):
        def __init__(self, frames):
            self.frames = frames

        def start(self):
            pass

        def rows(self):
            yield from self.frames

    for label, sample in samples.items():
        source = TsharkFeatureSource()
        frames = []
        for record in sample['replay']:
            body = {key: value for key, value in record.items() if key != 'row'}
            frames.append(Frame(features=source._features(body),
                                context=source._context(body)))
        builder = ContextFeatureSource(Replay(frames))
        builder.start()
        enriched = [frame.features for frame in builder.rows()]
        table = pd.DataFrame(enriched)
        features = _common.add_stage2_features(
            _common.build_mqtt_features(table), table, known_origins, known_topics)
        positions = {record['row']: index for index, record in enumerate(sample['replay'])}
        ordered = [positions[row] for row in sample['sample_rows']]
        expected_features = np.asarray(sample['expected_features'], dtype=float)
        actual_features = features.iloc[ordered].to_numpy(dtype=float)
        np.testing.assert_allclose(actual_features, expected_features,
                                   rtol=1e-6, atol=1e-6, equal_nan=True)
        tensor = _common.build_tensor(features.iloc[ordered], scaler, statistics,
                                      'parity ' + label)
        np.testing.assert_allclose(
            tensor, np.asarray(sample['expected_tensor'], dtype='float32'),
            rtol=1e-5, atol=1e-6)
        window = [enriched[position] for position in ordered]
        classifiers = {'xgboost': XgbClassifier, 'lstm': LstmClassifier,
                       'hybrid': HybridClassifier}
        for mode, classifier_type in classifiers.items():
            classifier = classifier_type(model_dir=str(export_dir), device='cpu')
            labels = classifier.predict(window)
            expected = sample['expected_labels_' + mode]
            if labels != expected:
                raise AssertionError('Paridad ' + label + '/' + mode + ': '
                                     + str(labels) + ' != ' + str(expected))
        report[label] = {'features': 'ok', 'tensor': 'ok',
                         'labels': {mode: 'ok' for mode in classifiers}}
        print('paridad', label, 'ok')
    return report


def write_report(output_dir, export_dir, parity, executed_path):
    metrics = json.loads((export_dir / 'metrics.json').read_text())
    config = json.loads((export_dir / 'pipeline_config.json').read_text())
    report = {
        'executed_notebook': str(executed_path),
        'package_dir': str(export_dir),
        'class_names': config.get('class_names'),
        'final_fold': config.get('evaluation', {}).get('final_fold'),
        'rotation_summary': metrics.get('rotation_summary'),
        'temporal': metrics.get('temporal'),
        'ablation_autoencoder_A_B_C': metrics.get('ablation_autoencoder_A_B_C'),
        'limitations': metrics.get('limitations'),
        'parity': parity,
        'note': ('No se copiaron artefactos a modelos_agente/. El usuario decide '
                 'tras revisar este informe.'),
    }
    path = output_dir / 'validation_report.json'
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print('Informe escrito en', path)


def main(argv=None):
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise SystemExit('El directorio de salida ya existe: ' + str(output_dir))
    output_dir.mkdir(parents=True)

    check_dependencies_and_data(data_dir)
    static_validation(root)
    compile_and_test(root)

    notebook = prepare_notebook(root, data_dir, output_dir, args.skip_ablation,
                                args.skip_temporal)
    executed_path = execute_notebook(notebook, output_dir, root)

    export_dir = output_dir / 'modelos_agente'
    if not export_dir.is_dir():
        raise SystemExit('El notebook no exportó el paquete candidato en ' + str(export_dir))
    parity = check_parity(export_dir, root)
    write_report(output_dir, export_dir, parity, executed_path)
    print('Validación final completa.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
