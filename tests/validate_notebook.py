"""Verifica el notebook con CSV locales y exporta solo a un directorio temporal.

--prepare: preparación y contratos. Sin flag: smoke con 1 epoch y 5 árboles;
sus métricas no representan el entrenamiento completo del notebook.
"""
import argparse
import json
import linecache
from pathlib import Path
import tempfile
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    notebook = json.loads((root / 'ml-mqtt-model.ipynb').read_text())
    namespace = {'__name__': '__main__'}
    with tempfile.TemporaryDirectory(prefix='mqtt-notebook-') as output:
        for index, cell in enumerate(notebook['cells']):
            if cell['cell_type'] != 'code':
                continue
            source = ''.join(cell['source'])
            if args.prepare and source.startswith('model_xgb ='):
                break
            for name in ('DoS',):
                source = source.replace(
                    f'/kaggle/input/datasets/alejandropenagos79/dataset/{name}.csv',
                    str(root / 'dataset' / f'{name}.csv'))
            source = source.replace("'/kaggle/working/modelos_agente'", repr(output))
            source = source.replace("'/kaggle/working/modelos_agente.zip'",
                                    repr(str(Path(output) / 'export.zip')))
            source = source.replace('n_estimators=100', 'n_estimators=5')
            filename = f'<mqtt-notebook-cell-{index}>'
            linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
            exec(compile(source, filename, 'exec'), namespace)
            if 'torch' in namespace:
                namespace['torch'].set_num_threads(2)
                namespace['EPOCHS'] = 1
                namespace['plt'] = None
        import numpy as np
        from infrastructure.classifiers._common import build_mqtt_features
        raw, features = namespace['df_raw'], namespace['X']
        np.testing.assert_allclose(features.to_numpy(), build_mqtt_features(raw).to_numpy())
        partitions = namespace['partitions']
        windows = namespace['window_rows']
        for name, rows in windows.items():
            assert np.isin(rows, partitions[name]).all()
            assert (namespace['direction_ids'][rows] ==
                    namespace['direction_ids'][rows[:, :1]]).all()
        assert 'frame.time_relative' not in features
        assert 'tcp.srcport' not in features
        assert 'mqtt.hdrflags' in features
        if not args.prepare:
            from composition_root import AgentConfig, build_agent
            from infrastructure.classifiers._frame import to_frame
            # Los tres adapters deben cargar los artefactos exportados y coincidir
            # con las predicciones del notebook sobre la misma ventana.
            indices = windows['test'][0]
            end = indices[-1]
            connection_rows = partitions['test'][
                namespace['direction_ids'][partitions['test']] ==
                namespace['direction_ids'][end]]
            connection_rows = np.sort(connection_rows)
            position = np.flatnonzero(connection_rows == end)[0]
            input_rows = connection_rows[position - 10:position + 1]
            assert len(input_rows) == 11
            window = raw.iloc[input_rows].to_dict('records')
            for mode in ('xgboost', 'lstm', 'hybrid'):
                agent = build_agent(AgentConfig(model_dir=output, model=mode))
                labels = agent.classifier.predict(window)
                assert labels and labels[-1] in ('normal', 'ataque')
                if mode == 'xgboost':
                    expected = namespace['model_xgb'].predict(features.iloc[[end]])[0]
                    assert labels[-1] == namespace['le_binary'].inverse_transform([expected])[0]
                if mode == 'hybrid':
                    expected = namespace['model_hybrid'].predict(namespace['hybrid']['test'].iloc[[0]])[0]
                    assert labels[-1] == namespace['le_binary'].inverse_transform([expected])[0]
            roundtrip = build_mqtt_features(to_frame(window))
            np.testing.assert_allclose(roundtrip.to_numpy(), features.iloc[input_rows].to_numpy())
        print('NOTEBOOK OK: preparación, separación de ventanas y contrato de features' +
              ('' if args.prepare else '; entrenamiento smoke, exportación y tres adapters'))


if __name__ == '__main__':
    main()
