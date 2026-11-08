# Contexto — Reorganización del notebook de detección DoS MQTT con features TCP

## 1. Para qué sirve este documento

Este documento es el contexto de traspaso para reorganizar el notebook del
proyecto. **La limpieza del dataset ya está hecha**; no se debe replantear. Lo
que falta es ordenar el notebook y separar responsabilidades en tres notebooks.

La decisión técnica ya está tomada: **el modelo final usa solo features TCP
(opción B)**. Las opciones A (features MQTT) y A' (B + MQTT) quedan únicamente
como evidencia experimental; A' no se vuelve a usar.

## 2. Contexto del proyecto

Detección de intrusiones sobre tráfico **MQTT/IoT**. El sistema tiene:

- Un **simulador** que publica tráfico normal y DoS contra Mosquitto.
- Un **sidecar de captura** (`infrastructure/tshark/stream_features.py`) que
  ejecuta `tshark` y escribe `features.jsonl`.
- Un **agente de detección** que consume ese JSONL, arma ventanas de 11 tramas
  por conexión y dirección, clasifica y publica alertas en `alertas/deteccion`.
- Un **agente de respuesta/bloqueo** descrito en el paper, pero **no
  implementado en este repositorio**. No forma parte de esta reorganización.

Arquitectura relevante:

```text
simulation/ → Mosquitto → capture (tshark) → features.jsonl
                                              ↓
                                   TsharkFeatureSource
                                              ↓
                                   Agent → Classifier → AlertSink
```

El agente actual sigue usando features MQTT (A). El modelo final TCP todavía no
está exportado ni integrado en el agente.

## 3. Decisión: usar TCP (B)

### Razón semántica

Un IDS debe usar comportamiento observable de red/transporte, no la presencia
de campos MQTT. Con MQTTS (TLS), `mqtt.*` no es observable. Un modelo que
depende de esas columnas solo sirve para MQTT en claro.

### Razón estadística

En el dataset, el normal es mayoritariamente no-MQTT y el DoS es mayoritariamente
MQTT. Un modelo con features MQTT aprende “es MQTT” en lugar de “es DoS”. Es un
sesgo inducido por la distribución del dataset, no una señal de ataque.

Evidencia en `df_scope` (puertos 1883/8883):

| Set | Macro-F1 | Recall DoS |
|---|---:|---:|
| A (13 features MQTT) | 0,9778 | 0,9813 |
| B (12 features TCP) | 0,9962 | 0,9972 |
| A' (B + MQTT), solo evidencia | 0,9973 | 0,9979 |
| B sin `tcp_new_conns_5s` | 0,9910 | 0,9937 |
| B sin `tcp_new_conns_5s` + `tcp_asymmetry_5s` | 0,9862 | 0,9892 |

Evidencia sobre todo el tráfico:

| Set | Macro-F1 |
|---|---:|
| A | 0,9915 |
| B | 0,9981 |
| A' (solo evidencia) | 0,9984 |
| B sin `tcp_new_conns_5s` | 0,9953 |

Conclusiones:

- B supera a A y queda a solo **0,0011** de A' en `df_scope`.
- Quitar las dos features TCP dominantes baja B **0,0100** en total; sigue
  superando a A y queda a **0,0111** de A'.
- La señal TCP está repartida: `frame.len`, `tcp_bytes_5s`, `tcp_len_std_5s`,
  `frame.time_delta`, `tcp_frames_5s`.
- En todo el tráfico, `tcp_asymmetry_5s` y `fe_is_standard_mqtt_port` parecen muy
  predictivas porque separan normal no-MQTT de DoS MQTT. Dentro de `df_scope`, la
  bandera de puerto es constante y la asimetría baja de AUC 0,970 a 0,829. Es el
  atajo de protocolo que se quiere evitar.

### Límite pendiente

Solo hay **una captura DoS** (`DoS.csv`): 45.330 frames, 886 conexiones y
~36.787 ventanas DoS. El F1 alto es válido para ese escenario, no para cualquier
DoS. Falta validar en caliente con el simulador, que usa conexiones persistentes
y no un flood de conexiones nuevas.

## 4. Estado del notebook actual

`ML_Model/ml-mqtt-model.ipynb` tiene **65 celdas**:

| Celdas | Contenido |
|---|---|
| 0–5 | Título, imports y carga |
| 6–27 | EDA, política de columnas, nulos, tipos MQTT, puertos |
| 28–31 | Aplicar política y construir la matriz A |
| 32–50 | Experimentos 2.8–2.11: scope, A/B/A', ablaciones y AUC |
| 51–64 | Secciones 3–9: modelos A (XGBoost, LSTM, híbrido) y export A |

Problemas:

- Los experimentos A/B/A' están dentro del EDA.
- Las secciones 51–64 entrenan y exportan **A (MQTT)**, no B.
- No existe modelo final B ni export TCP.
- Las secciones 5–7 referencian `optuna`, `torch`, `nn`, `DataLoader` y
  `XGB_DEVICE` comentados o no definidos; el notebook no corre de arriba a abajo.
- Hay imports duplicados y numeración inconsistente (`2.9.5`, luego 2.10 y 2.11).
- Hay rutas de Kaggle mezcladas con rutas locales.
- Solo hay outputs hasta la celda 50; el modelado no se ejecutó.

## 5. Decisiones de reorganización

- **Tres notebooks**:
  1. `01_eda_politica.ipynb`: EDA, política, decisiones y artefacto limpio.
  2. `02_tcp_vs_mqtt.ipynb`: comparación **A vs B**, sin A'.
  3. `03_modelo_tcp.ipynb`: modelo final B, ablaciones movidas allí, sin A', y
     export TCP.
- **Notebook 2:** solo A/B; se elimina A' de todas las celdas.
- **Notebook 3:** incluye las ablaciones 2.10/2.11, adaptadas sin A'; el foco es
  B y sus variantes.
- **Notebook 1** guarda `ML_Model/artifacts/df_raw.joblib` y `manifest.json`.
  **Notebooks 2 y 3 los cargan**.
- **Backup obligatorio** antes de borrar: `ML_Model/backup/ml-mqtt-model.backup.ipynb`.
- **Celdas 51–64 se eliminan** de los notebooks nuevos; quedan solo en el backup.
- **Export TCP** primero a `modelos_agente_tcp/`; después de validar, reemplazar
  `modelos_agente/`.
- **Hiperparámetros fijos**, sin Optuna:
  `n_estimators=300`, `learning_rate=0.05`, `max_depth=4`,
  `min_child_weight=2.0`, `subsample=0.9`, `colsample_bytree=0.9`,
  `reg_lambda=1.0`, `tree_method='hist'`.
- `plans/` vive en la raíz del repositorio.

## 6. Estructura objetivo

```text
ML_Model/
  backup/
    ml-mqtt-model.backup.ipynb
  artifacts/
    df_raw.joblib
    manifest.json
  01_eda_politica.ipynb
  02_tcp_vs_mqtt.ipynb
  03_modelo_tcp.ipynb

plans/
  00_contexto.md
  01_eda_politica.md
  02_tcp_vs_mqtt.md
  03_modelo_tcp.md
```

**Formato del artefacto:** `df_raw.joblib` con `joblib.dump`. Se prefiere sobre
Parquet porque conserva los tuples de `_connection` y `_direction`. El
`manifest.json` guarda conteos, columnas, hash, semilla y versión de features.

## 7. Qué no se debe hacer

- No reintroducir A' en ningún notebook.
- No volver a usar `mqtt.*` como features del modelo final.
- No borrar el normal no-MQTT para “limpiar” el sesgo: eso crearía un dataset
  artificial. La limpieza ya está hecha; el sesgo se evita con TCP.
- No tocar el agente, el simulador ni `modelos_agente/` en esta fase de
  reorganización de notebooks.
- No crear notebooks en este paso: solo se están documentando los planes.

## 8. Siguiente fase (fuera de estos planes)

Cuando los notebooks estén ordenados, el trabajo pendiente es:

1. Implementar un builder incremental de features TCP y un adaptador
   `TcpXgbClassifier` para el agente.
2. Exportar e integrar el modelo B en `modelos_agente/`.
3. Validar en caliente con el simulador: normal, DoS persistente, distintas
   tasas/clientes/payloads y TLS en 8883.
4. Implementar el agente de respuesta/bloqueo, que hoy no existe en el repo.
