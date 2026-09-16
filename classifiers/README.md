# `classifiers/` — Classifiers (Adapters)

Adaptadores que implementan el *port* `core.protocols.Classifier`
(`predict(window) -> list[str]`) y delegan la inferencia real en `MQTTDetector`
(`agent_inference.py`).

Patrón: **Adapter** (envuelven `MQTTDetector` para exponer una interfaz uniforme) y
**Strategy** (cada uno usa un modelo distinto; se eligen por configuración).

`predict` devuelve **una etiqueta por frame evaluable**; el agente toma la **última**
(`labels[-1]`), que corresponde a la fila más reciente de la ventana.

## Inyección

Cada clasificador tiene la firma:

```python
Cls(model_dir: str | None = None, detector=None, device: str | None = None)
```

- `detector` — si se pasa, se usa directamente (tests / compartir una única carga).
- `model_dir` — si no, importa `MQTTDetector` de forma **lazy** y lo carga de disco.

El import es perezoso para que `import classifiers` no requiera `torch`/`xgboost`.

## `_frame.py`

- **`to_frame(window) -> pandas.DataFrame`** — convierte una secuencia de `FeatureRow`
  en un `DataFrame` con las **7 columnas** de `core.FEATURE_COLUMNS`, en orden fijo;
  añade con `0.0` las que falten. Es el puente entre `FeatureRow` y `MQTTDetector`.

## `hybrid.py` — `HybridClassifier`

- Llama a `MQTTDetector.predecir_hibrido`: XGBoost + `fe_lstm_mse` (error del LSTM).
- Es el modelo por defecto del agente (`--model hybrid`).
- Solo necesita las 7 features de red → ideal para el escenario cifrado.

## `tls_xgb.py` — `TlsXgbClassifier`

- Llama a `predecir_tls`: XGBoost entrenado con features de red/transporte.
- Alternativa sin LSTM.

## `case1.py` — `Case1Classifier`

- Llama a `predecir_caso1`: XGBoost con **todas** las features del dataset.
- Con una ventana de 7 columnas, las ausentes se rellenan (`NOT_MQTT`/`-1`), por lo que
  su uso en el agente es de referencia, no el recomendado para tráfico cifrado.

## `anomaly.py` — `AnomalyClassifier`

- Llama a `predecir_anomalia` (LSTM Autoencoder) y traduce el flag binario.
- Constantes: `LABEL_NORMAL = 'normal'`, `LABEL_ANOMALY = 'ataque'`.
- `1` → `'ataque'`, `0` → `'normal'`.

## `__init__.py`

Reexporta `AnomalyClassifier`, `Case1Classifier`, `HybridClassifier` y
`TlsXgbClassifier`.
