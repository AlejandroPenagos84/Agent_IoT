# Fase 0 — diagnóstico y reproducción de línea base

Fecha de ejecución: 2026-09-21.

Esta fase no modifica el modelo ni las features. Se ejecutó una copia de
`ml-mqtt-model.ipynb` con las rutas locales sustituidas para leer los CSV reales
de `data/` y escribir todos los artefactos en `tmp/fase0/`. El notebook original
y `modelos_agente/` no fueron modificados.

## 0.0 Línea base reproducida

Entorno: Python 3.11.16, NumPy 2.4.6, pandas 3.0.5, scikit-learn 1.9.1,
XGBoost 3.2.0 y PyTorch 2.14.0+cu130 sobre CPU. Se conservaron `SEED = 42`,
`N_SPLITS = 5`, `SEQ_LEN = 10` y 10 épocas.

La primera combinación válida seleccionada por el notebook fue:

- test: fold 1 (índice 0);
- validation: fold 2 (índice 1);
- train: folds 3, 4 y 5 (índices 2, 3 y 4).

Todos los splits contienen las cuatro clases a nivel de frame y de última fila
de ventana. Sin embargo, validation y test contienen solamente **una conexión
con frames MitM cada uno**, por lo que sus métricas MitM tienen poca
independencia estadística.

### Métricas medidas

| Modelo | Frames | Accuracy | Bal. acc. | Macro-F1 | AUC | FP normal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| XGBoost (todos) | 51.946 | 0,9889 | 0,9886 | 0,9817 | 0,9994 | 1,0920 % |
| XGBoost (con ventana) | 39.559 | 0,9931 | 0,9912 | 0,9889 | 0,9997 | 0,5753 % |
| LSTM | 39.559 | 0,9598 | 0,9561 | 0,9386 | 0,9723 | 3,7858 % |
| Híbrido | 39.559 | 0,9952 | 0,9929 | 0,9923 | 0,9995 | 0,3408 % |

El umbral LSTM calibrado exclusivamente con ventanas normales de validation fue
`1,2811753749847412`.

### Línea base declarada frente a la medida

| Modelo | Frames declarados → medidos | Bal. acc. declarada → medida | Macro-F1 declarada → medida | AUC declarada → medida |
| --- | ---: | ---: | ---: | ---: |
| XGBoost (todos) | 45.599 → 51.946 | 0,983 → 0,9886 | 0,983 → 0,9817 | 0,995 → 0,9994 |
| XGBoost (con ventana) | 33.210 → 39.559 | 0,985 → 0,9912 | 0,989 → 0,9889 | 0,994 → 0,9997 |
| LSTM | 33.210 → 39.559 | 0,917 → 0,9561 | 0,899 → 0,9386 | 0,926 → 0,9723 |
| Híbrido | 33.210 → 39.559 | 0,985 → 0,9929 | 0,989 → 0,9923 | 0,994 → 0,9995 |

La línea base declarada **no se reprodujo exactamente**. La causa directamente
observable es que la partición medida tiene 51.946 frames de test y 39.559
ventanas, frente a 45.599 y 33.210 declarados. Esto puede provenir de una
ejecución anterior con otra versión de los CSV, del código de agrupación o de
`StratifiedGroupKFold`; no hay evidencia suficiente para atribuirlo a una sola
causa. Además, el CSV actual contiene 45.514 frames DoS, uno más que los 45.513
documentados. Para las fases siguientes, los valores medidos de esta sección
son el “Antes”.

## 0.1 Población antes y después del filtro

Las causas pueden solaparse; por ello, sus columnas no deben sumarse. “Sin
puerto” también incluye valor ausente, fuera de rango o no entero.

| Captura | Clase | Originales | IPv4/TCP | Descartados | Sin `ip.src` | Sin `ip.dst` | Sin puerto origen | Sin puerto destino | Sin epoch |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DoS | DoS | 45.514 | 45.460 | 54 (0,12 %) | 23 | 23 | 54 | 54 | 0 |
| DoS | normal | 49.111 | 43.000 | 6.111 (12,44 %) | 1.010 | 1.010 | 6.111 | 6.111 | 0 |
| MitM | mitm | 3.855 | 380 | **3.475 (90,14 %)** | **3.473** | **3.473** | **3.475** | **3.475** | 0 |
| MitM | normal | 106.813 | 99.134 | 7.679 (7,19 %) | 4.760 | 4.760 | 7.679 | 7.679 | 0 |
| Intrusion | intrusion | 1.898 | 1.894 | 4 (0,21 %) | 2 | 2 | 4 | 4 | 0 |
| Intrusion | normal | 78.995 | 69.863 | 9.132 (11,56 %) | 3.785 | 3.785 | 9.132 | 9.132 | 0 |

El filtro deja 259.731 de 286.186 frames. El hallazgo principal es que elimina
el 90,14 % de MitM, compatible con la observación previa de que gran parte de
esa clase carece de IP y puertos TCP.

## 0.2 Recall por tipo de ataque

El recall condicionado usa únicamente ejemplos evaluables del test. En LSTM la
etiqueta binaria sigue siendo `any-in-window`, mientras que el tipo se toma de
la última fila; en el híbrido se usa `last-frame`.

| Modelo | Tipo | Evaluables test | Detectados | Recall condicionado | Frames descartados (dataset) | Recall e2e literal |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | DoS | 9.092 | 9.053 | 0,9957 | 54 | 0,1989 |
| XGBoost | MitM | 77 | 12 | 0,1558 | 3.475 | 0,0031 |
| XGBoost | intrusion | 378 | 368 | 0,9735 | 4 | 0,1939 |
| LSTM | DoS | 7.487 | 7.265 | 0,9703 | 54 | 0,1596 |
| LSTM | MitM | 71 | 17 | 0,2394 | 3.475 | 0,0044 |
| LSTM | intrusion | 17 | 13 | 0,7647 | 4 | 0,0068 |
| Híbrido | DoS | 7.487 | 7.475 | 0,9984 | 54 | 0,1642 |
| Híbrido | MitM | 71 | 10 | 0,1408 | 3.475 | 0,0026 |
| Híbrido | intrusion | 17 | 9 | 0,5294 | 4 | 0,0047 |

“Recall e2e literal” aplica literalmente `detectados en test / todos los frames
de ataque originales`. Es un **límite inferior conservador**, no un estimador
held-out estándar: los frames descartados carecen de endpoints y no pueden
asignarse a los folds agrupados por conexión; además, el denominador contiene
todo el dataset y el numerador solo test. No se extrapoló el recall de test al
resto de datos ni se evaluó sobre train para inflar el resultado. Resolver una
métrica e2e por fold requeriría una regla de asignación para frames sin conexión,
que hoy no existe.

## 0.3 Conexiones y frames por partición

| Partición | Clase | Conexiones | Frames |
| --- | --- | ---: | ---: |
| train | DoS | 550 | 27.276 |
| train | mitm | 5 | 273 |
| train | intrusion | 247 | 1.137 |
| train | normal | 2.215 | 127.198 |
| train | **TOTAL** | **2.816** | **155.884** |
| validation | DoS | 178 | 9.092 |
| validation | mitm | **1** | 30 |
| validation | intrusion | 83 | 379 |
| validation | normal | 737 | 42.400 |
| validation | **TOTAL** | **939** | **51.901** |
| test | DoS | 179 | 9.092 |
| test | mitm | **1** | 77 |
| test | intrusion | 84 | 378 |
| test | normal | 736 | 42.399 |
| test | **TOTAL** | **935** | **51.946** |

Los conteos de conexiones por clase pueden solaparse cuando una `_connection`
contiene más de una etiqueta; por eso no suman necesariamente el total.

| Partición | Ventanas totales | DoS | MitM | Intrusion | Normal |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 118.663 | 22.411 | 261 | 51 | 95.940 |
| validation | 39.507 | 7.466 | 30 | 17 | 31.994 |
| test | 39.559 | 7.487 | 71 | 17 | 31.984 |

Aunque hay muchos frames, MitM en validation/test y las ventanas Intrusion no
tienen cobertura independiente suficiente para conclusiones robustas.

## 0.4 `mqtt.hdrflags`

No hay valores con comas: 0 de 286.186 frames (0 %), y 0 conversiones
silenciosas a NaN por este motivo. Los 47.972 valores no vacíos son hexadecimales
escalares como `0x000000c0`; el helper `number` del notebook sí los interpreta y
ninguno queda sin convertir.

## 0.5 `mqtt.len`

No hay valores con comas: 0 de 286.186 frames (0 %), y 0 conversiones
silenciosas a NaN. Los 47.972 valores no vacíos son escalares numéricos.

## 0.6 `mqtt.msg`

Hay 41.789 valores no vacíos. Aunque muchos usan exclusivamente caracteres del
alfabeto hexadecimal, la evidencia de longitud indica que son **texto** y no una
representación hexadecimal de bytes: en los 41.726 casos comparables,
`mqtt.len - mqtt.topic_len - 2` coincide con el número de caracteres en los
41.726 casos y con la mitad de esa longitud en 0 casos. Ejemplos cortos reales:
`0`, `1`, `132`, `400`; los mensajes largos son cadenas alfanuméricas como
`4BC1bAa76E8c...`.

Por tanto, para estos CSV la entropía actual sobre caracteres no está calculada
sobre texto hexadecimal que deba decodificarse primero. Los 63 casos no
comparables no permiten cambiar esta conclusión general, pero quedan fuera de
la comprobación de longitud.

## 0.7 Asserts de afirmaciones actuales

| Afirmación | Comparables | Iguales exactos | Distintos |
| --- | ---: | ---: | ---: |
| `frame.cap_len == frame.len` | 286.186 | 286.186 | 0 |
| `frame.time_delta_displayed == frame.time_delta` | 286.186 | 286.186 | 0 |

Las columnas declaradas constantes cumplen `nunique(dropna=True) <= 1`:

| Columna | `nunique` | Valor observado |
| --- | ---: | --- |
| `frame.encap_type` | 1 | `1` |
| `frame.ignored` | 1 | `0` |
| `frame.marked` | 1 | `0` |
| `frame.offset_shift` | 1 | `0.0` |

## 0.8 Features actuales comprobadas

- `fe_cap_ratio = frame.cap_len / frame.len`: 286.186 valores válidos, un único
  valor (`1,0`) y 0 valores distintos de 1.
- `fe_anon_connect`, calculada para este diagnóstico como
  `mqtt.msgtype == 1` y `mqtt.clientid` ausente/vacío: 0 positivos de 286.186
  (0 %) en todas las clases.

La definición de `fe_anon_connect` no existe como función en el notebook actual;
se hizo explícita aquí para que el resultado sea reproducible y no dependa de
una descripción ambigua.

## 0.9 `fe_bytes_per_sec`

La implementación actual es exactamente:

```python
frame.len / (frame.time_delta + 1e-6)
```

Es una tasa instantánea aproximada basada en el delta del frame, no bytes por
segundo de una ventana. Sobre los 259.731 frames seleccionados: mínimo 6,934;
mediana 1.213.114,754; percentil 95 32.212.765,957; percentil 99
68.818.181,818; máximo 134.000.000.

El notebook consume `frame.time_delta` precalculado en el CSV antes de filtrar.
En despliegue, `stream_features.py` exporta el valor calculado por tshark y
`TsharkFeatureSource` lo transmite; el agente no recalcula deltas sobre los
frames filtrados. Con el Compose actual (`--filter ""`) no se observó una
diferencia de fórmula: tanto entrenamiento como despliegue dependen del delta de
captura. Una captura desplegada con otro capture/display filter podría cambiar
la población observada y debe verificarse por separado.

## Qué se ejecutó

- Notebook original copiado mediante `nbformat`; solo se sustituyeron las tres
  rutas Kaggle por `/workspace/data/*.csv` y `OUT_DIR`/ZIP por
  `/workspace/tmp/fase0/`.
- Celdas de código originales 1, 3, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20 y 22,
  más una celda 24 de diagnóstico sin cambios de entrenamiento.
- Los tres CSV reales: `DoS.csv`, `MitM.csv` e `Intrusion.csv`.
- Partición `test_fold=0`, `val_fold=1`, train folds 2/3/4.
- XGBoost de frames, LSTM autoencoder, híbrido y XGBoost restringido a frames
  con ventana.
- Validación de esquema del notebook ejecutado con `nbformat` y serialización
  del diagnóstico con `allow_nan=False`.

Archivos reproducibles:

- `tmp/fase0/ml-mqtt-model-fase0.ipynb`;
- `tmp/fase0/ml-mqtt-model-fase0-executed.ipynb`;
- `tmp/fase0/diagnostics.json`;
- `tmp/fase0/modelos_agente/` (artefactos temporales de esta ejecución).

## Qué no se ejecutó

- No se usaron datos sintéticos y no se creó `tests/make_synthetic.py`.
- No se ejecutaron las fases 1–5.
- No se modificó ni reexportó `modelos_agente/` del proyecto.
- No se hizo rotación de cinco folds ni split temporal/episódico; corresponden a
  la Fase 5.
- No se probó la captura de red en vivo ni un broker.

## Qué continúa sin verificar

- La causa histórica exacta de la diferencia frente a la línea base declarada.
- El mecanismo exacto de etiquetado de MitM e Intrusion del dataset.
- Generalización de MitM: validation y test tienen una sola conexión de esa
  clase cada uno.
- Un recall extremo a extremo held-out por fold para frames sin endpoints, ya
  que no existe una regla causal de conexión/partición para asignarlos.
- Diferencias de contexto entre entrenamiento por partición y despliegue
  continuo; todavía no hay features de contexto por origen.
- Comportamiento con tráfico MQTTS real; el diagnóstico utiliza los CSV de
  MQTT_UAD disponibles.

## Decisión requerida

La Fase 0 queda cerrada. Antes de continuar hay que elegir una opción:

- **A — ampliar a frames no IP/L2:** permite estudiar las ráfagas y
  broadcast/multicast donde aparece gran parte de MitM, pero obliga a redefinir
  población, agrupación de episodios L2, particiones, captura y línea base.
- **B — mantener IPv4/TCP:** conserva la arquitectura actual; MitM basado en
  ARP/L2 queda explícitamente fuera del alcance y se debe seguir reportando
  recall extremo a extremo.

No se implementó ninguna opción automáticamente.

> Decisión posterior: se eligió **A**. La nueva población, agrupación y línea
> base están documentadas en `reports/fase0-opcion-a.md`.
