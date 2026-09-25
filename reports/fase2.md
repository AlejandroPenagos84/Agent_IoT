# Fase 2 — Novedad de cliente para intrusion

Fecha de ejecución: 2026-09-21.

Esta fase añade `fe_origen_conocido` (Etapa 2, después del split) y exporta el
artefacto `known_origins.json`. El modelo sigue siendo binario. No se cambian
particiones, features de Etapa 1, calibración del umbral ni la semántica de
etiquetas. Se construye sobre la Fase 1 (pesos balanceados por cuatro clases),
por lo que la comparación “Antes → Después” aísla el efecto de la nueva feature.

## Cambio implementado

Notebook `ml-mqtt-model.ipynb`:

- `BASE_FEATURE_COLUMNS` (13, Etapa 1) y
  `FEATURE_COLUMNS = BASE + ['fe_origen_conocido']` (14).
- Tras definir `train_idx/val_idx/test_idx`, allowlist **solo con normal de train**:
  claves prefijadas `ip:<ip.src>` y `client:<mqtt.clientid>`;
  `fe_origen_conocido = 1` si la IP **o** el client_id del frame están en el
  conjunto, si no `0`.
- `X_stage1` se calcula antes del split; la columna se añade después y el
  escalado/LSTM usan ya las 14 features.

Infraestructura (para reproducción en streaming):

- `infrastructure/classifiers/_common.py`: `BASE_MODEL_FEATURES`,
  `MODEL_FEATURES` (14), `add_known_origin_feature`, `load_known_origins`;
  `build_case1`/`build_lstm_raw` reciben `known_origins`.
- `xgb.py`, `hybrid.py`, `anomaly.py`: cargan la allowlist en `__init__`.
- `infrastructure/tshark/tshark_feature_source.py`: transporta `_origin_ip` como
  entrada interna; `tshark_schema.py` la declara fuera de las features crudas.
- `tests/test_agent_windows.py` y `tests/validate_notebook.py` actualizados.

## Artefacto `known_origins.json`

- 610 claves = **584 `ip:`** + **26 `client:`**, aprendidas de **140.952 frames
  normales de train**.
- Formato:
  `{version, derived_from: 'normal frames in train partition only',
  key_types: ['ip','client'], keys: [...]}`.
- `pipeline_config.json` declara `known_origins_artifact`, `feature_stages` y
  `known_origin_state`.
- Umbral LSTM calibrado solo con normal de validación: `1,3730154037475586`.

## Partición

Idéntica a Fase 0 opción A y Fase 1: `SEED = 42`, `test_fold = 0`,
`val_fold = 1`, `train_folds = 2, 3, 4`. Tamaños: train 171.526, val 57.484,
test 57.176.

## Distribución de `fe_origen_conocido`

| Partición | Clase | Frames | Conocidos | Desconocidos | % conocido |
| --- | --- | ---: | ---: | ---: | ---: |
| train | DoS | 27.309 | 27.294 | 15 | 99,95 % |
| train | intrusion | 1.139 | 1.137 | 2 | 99,82 % |
| train | mitm | 2.126 | 299 | 1.827 | 14,06 % |
| train | normal | 140.952 | 135.010 | 5.942 | 95,78 % |
| val | DoS | 9.102 | 9.092 | 10 | 99,89 % |
| val | intrusion | 379 | 379 | 0 | 100,00 % |
| val | mitm | 1.020 | 0 | 1.020 | 0,00 % |
| val | normal | 46.983 | 43.629 | 3.354 | 92,86 % |
| test | DoS | 9.103 | 9.097 | 6 | 99,93 % |
| test | **intrusion** | 380 | **380** | **0** | **100,00 %** |
| test | mitm | 709 | 83 | 626 | 11,71 % |
| test | normal | 46.984 | 32.466 | 14.518 | 69,10 % |

Por tipo de observación (test): TCP 76,25 % conocido; L2 44,02 % conocido. La
mayoría de los “desconocidos” de test son frames **normales** (14.518) y MitM-L2
(626); solo 6 DoS y **0 intrusion**.

## Antes → después

“Antes” = `reports/fase1.md` (misma partición, mismos pesos). “Después” =
`tmp/fase2/diagnostics.json`.

### XGBoost (todos los frames)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9729 | 0,9732 | +0,0004 |
| Macro-F1 | 0,9390 | 0,9395 | +0,0005 |
| AUC | 0,9977 | 0,9977 | +0,0000 |
| Recall DoS | 0,9932 | 0,9932 | +0,0000 |
| Recall MitM | 0,9605 | 0,9676 | +0,0071 |
| Recall intrusion | 0,9789 | 0,9789 | +0,0000 |
| FP normal | 4,4653 % | 4,4377 % | −0,0277 pp |

### XGBoost (frames con ventana)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9797 | 0,9798 | +0,0001 |
| Macro-F1 | 0,9559 | 0,9563 | +0,0004 |
| AUC | 0,9991 | 0,9991 | −0,0001 |
| FP normal | 3,4156 % | 3,3802 % | −0,0355 pp |

### LSTM

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9252 | 0,9245 | −0,0006 |
| Macro-F1 | 0,9213 | 0,9198 | −0,0015 |
| AUC | 0,9259 | 0,9455 | **+0,0196** |
| Recall DoS (cond.) | 0,9664 | 0,9664 | +0,0000 |
| Recall MitM (cond.) | 0,0329 | 0,0347 | +0,0017 |
| Recall intrusion (cond.) | 0,7222 | 0,7222 | +0,0000 |
| FP normal | 3,4506 % | 3,5907 % | +0,1401 pp |

### Híbrido LSTM + XGBoost

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9876 | 0,9865 | −0,0012 |
| Macro-F1 | 0,9762 | 0,9732 | −0,0030 |
| AUC | 0,9986 | 0,9982 | −0,0003 |
| Recall DoS | 0,9953 | 0,9953 | +0,0000 |
| Recall MitM | 0,9601 | 0,9636 | +0,0035 |
| Recall intrusion | 0,7222 | 0,6667 | −0,0556 |
| FP normal | 1,6886 % | 1,9370 % | +0,2484 pp |

## Recall por tipo (Fase 2)

| Modelo | Tipo | Frames test | Evaluables | Detectados | Recall cond. | Recall e2e test |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | DoS | 9.103 | 9.103 | 9.041 | 0,9932 | 0,9932 |
| XGBoost | MitM | 709 | 709 | 686 | 0,9676 | 0,9676 |
| XGBoost | intrusion | 380 | 380 | 372 | 0,9789 | 0,9789 |
| LSTM | DoS | 9.103 | 7.466 | 7.215 | 0,9664 | 0,7926 |
| LSTM | MitM | 709 | 577 | 20 | 0,0347 | 0,0282 |
| LSTM | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |
| Híbrido | DoS | 9.103 | 7.466 | 7.431 | 0,9953 | 0,8163 |
| Híbrido | MitM | 709 | 577 | 556 | 0,9636 | 0,7842 |
| Híbrido | intrusion | 380 | 18 | 12 | 0,6667 | 0,0316 |

Semánticas: XGBoost `frame`; LSTM `any-in-window; tipo=last-frame`; híbrido
`last-frame`.

## Interpretación

- **La feature no aporta novedad para intrusion**: en test, sus 380 frames tienen
  `fe_origen_conocido = 1` (0 desconocidos). Como la allowlist se deriva de normal
  de train y las identidades de intrusion ya aparecen en normal, el lookup no
  distingue al atacante. Es el caso de “casi trivial” que advierte el CLAUDE.md,
  pero en la dirección de no separar.
- En test, los “desconocidos” son mayoritariamente `normal` (14.518) y MitM-L2
  (626). Es coherente con que el FP de `normal` suba en LSTM (+0,14 pp) e híbrido
  (+0,25 pp): la feature actúa sobre todo como proxy de “TCP vs L2”, no de intruso.
- La subida de AUC del LSTM (+0,0196) viene acompañada de caída de balanced
  accuracy y macro-F1; MitM mejora levemente e intrusion no cambia. No se atribuye
  a novedad de identidad.
- El híbrido pierde recall de intrusion (0,7222 → 0,6667) sobre solo 18 ventanas
  evaluables (una detección menos); no es concluyente.

Advertencias que deben acompañar a esta feature:

> `fe_origen_conocido` mide novedad de identidad y puede ser casi trivial en este
> dataset. Es una lista de permitidos derivada de train, no una representación
> completa del comportamiento.

> Si un atacante suplanta una identidad/origen conocido, esta señal deja de
> distinguirlo.

No se presenta como una detección general de Intrusion. La Fase 2 no fija
criterios numéricos de aceptación; se reporta el antes/después y la cobertura.

## Qué se ejecutó

- Notebook completo sobre los tres CSV reales, 100 árboles y 10 épocas, en CPU.
- XGBoost de frames, LSTM autoencoder, híbrido y XGBoost con ventana.
- Diagnóstico de cobertura de `fe_origen_conocido` por partición, clase y
  observación.
- Cambios de infraestructura (`_common`, `xgb`, `hybrid`, `anomaly`, schema,
  `tshark_feature_source`) y tests actualizados.
- Entorno: Python 3.11.16, NumPy 2.4.6, pandas 3.0.5, XGBoost 3.2.0,
  PyTorch 2.14.0+cu130 sobre CPU. El notebook ejecutó sin errores.
- Verificación posterior en contenedor: carga de los tres adaptadores contra
  `tmp/fase2/modelos_agente/` (`XgbClassifier`, `AnomalyClassifier` y
  `HybridClassifier` predicen y cargan 610 claves de `known_origins.json`).
- Suite `python -m unittest discover -s tests -v`: 27 pruebas, 26 correctas y
  1 omitida (tshark no instalado). No crea artefactos persistentes.

Archivos reproducibles:

- `tmp/fase2/ml-mqtt-model-fase2.ipynb` / `-executed.ipynb`;
- `tmp/fase2/diagnostics.json`;
- `tmp/fase2/modelos_agente/` (9 artefactos, incluido `known_origins.json`).

## Qué no se ejecutó

- **No se actualizaron los artefactos de `./modelos_agente/`.** Siguen siendo los
  de 13 features sin `known_origins.json`, mientras el código ya espera 14
  features y el artefacto. `composition_root.build_agent` fallaría al cargarlos:
  el conjunto de artefactos está **inconsistente** (restricción 7).
- No se ejecutó tráfico real, broker ni MQTTS.
- No se hizo ablación intra-corrida “sin/con”; el “sin” es la Fase 1.
- No se hizo rotación de folds ni split temporal/episódico (Fase 5).

## Qué continúa sin verificar

- Por qué las identidades de intrusion ya están en normal de train; mecanismo de
  etiquetado del dataset.
- Efecto separado de `ip.src` y de `mqtt.clientid` propagado (se probó como unión).
- Validez de una allowlist fija en despliegue y su comportamiento cuando el
  atacante suplanta un origen visto.
- Diferencias entre orígenes conocidos por partición y el contexto continuo de
  despliegue.
- La reproducción en streaming end-to-end (captura tshark real): solo se verificó
  la carga y predicción de los adaptadores contra `tmp/fase2/modelos_agente/`.
