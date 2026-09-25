# Fase 3 — Contexto causal

Fecha de ejecución: 2026-09-21.

Esta entrega implementa **solo la Fase 3.1 (contexto de CONNECT)** y documenta la
**Fase 3.2 (nota sobre `_connection`)**. Las fases 3.3–3.6 quedan pendientes y se
resumen al final. La Fase 3.1 se mide contra la Fase 2 (misma partición, mismos
pesos de cuatro clases), por lo que el “Antes → Después” aísla sus cuatro
features nuevas.

## 3.1 Contexto de CONNECT

### Objetivo

Propagar de forma causal, desde el CONNECT hacia los frames posteriores de la
misma conexión: versión MQTT, keep-alive, clean session y longitud del clientid.
Es Etapa 1 (antes del split), porque el estado no cruza particiones.

### Implementación

Notebook `ml-mqtt-model.ipynb`:

- `CONNECT_CONTEXT` declara los pares `(feature, columna de transporte, columna
  cruda)`.
- `add_connect_context(df)` hace **forward-fill causal** de `mqtt.ver`,
  `mqtt.kalive`, `mqtt.conflag.cleansess` y `mqtt.clientid_len` agrupando por
  `_connection` (sin mirar frames futuros).
- `build_mqtt_features` añade las cuatro features `fe_mqtt_ver`,
  `fe_mqtt_kalive`, `fe_mqtt_cleansess`, `fe_mqtt_clientid_len` (con `nan_fill`
  cuando no hay CONNECT).
- Las features entran en `BASE_FEATURE_COLUMNS`, así que la matriz pasa de 14 a
  **18 features** (17 de Etapa 1 + `fe_origen_conocido`).

Infraestructura (reproducción en streaming):

- `_common.CONNECT_CONTEXT` + `BASE_MODEL_FEATURES` (mismas 17 de Etapa 1).
- `TsharkFeatureSource` mantiene `_connect_state` por `tcp.stream` y lo inyecta
  como `_connect_*` en cada fila, con `_resolve_connect` actualizando el estado
  en el CONNECT (`mqtt.msgtype == 1`).
- `tshark_schema.FEATURE_COLUMNS` transporta `_connect_*` sin exponerlas al
  modelo.
- `pipeline_config.json` declara `stream_state.connect_context` (features,
  fuentes, método y reset).

### Causalidad y diferencia entrenamiento/despliegue

- Offline el forward-fill se hace por `_connection` (endpoints `IP:puerto` +
  contador acumulado de CONNECT), porque el dataset **no incluye `tcp.stream`**.
- Online el agente correlaciona por `tcp.stream` de tshark.
- Ambas son aproximaciones de sesión equivalentes en intención, pero **no
  idénticas en el mecanismo**; la comparación se documenta en 3.2.
- La reconstrucción offline se verificó en el diagnóstico:
  `reconstruction_checked: true` (las 4 features coinciden con el forward-fill
  recomputado desde `_connection`).

### Cobertura (proporción con contexto propagado)

Las cuatro features comparten exactamente la misma cobertura.

| Partición | Clase | Frames | Propagados | % |
| --- | --- | ---: | ---: | ---: |
| train | DoS | 27.309 | 14.527 | 53,19 % |
| train | intrusion | 1.139 | 933 | 81,91 % |
| train | mitm | 2.126 | 60 | 2,82 % |
| train | normal | 140.952 | 5.411 | 3,84 % |
| val | DoS | 9.102 | 4.911 | 53,96 % |
| val | intrusion | 379 | 324 | 85,49 % |
| val | mitm | 1.020 | 0 | 0,00 % |
| val | normal | 46.983 | 2.818 | 6,00 % |
| test | DoS | 9.103 | 4.739 | 52,06 % |
| test | intrusion | 380 | 309 | 81,32 % |
| test | mitm | 709 | 0 | 0,00 % |
| test | normal | 46.984 | 1.591 | 3,39 % |

Por observación (test): TCP 12,69 %; L2 0,00 %. La cobertura es alta en
intrusion/DoS porque son conexiones TCP/MQTT; es nula en MitM (L2) y baja en
`normal`, que incluye mucho tráfico no MQTT. Por tanto, parte de la señal de
estas features es un proxy de “sesión TCP MQTT con CONNECT”, no de ataque.

### Antes → después

“Antes” = `reports/fase2.md` (misma partición). “Después” = `tmp/fase3/diagnostics.json`.

#### XGBoost (todos los frames)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9732 | 0,9756 | +0,0024 |
| Macro-F1 | 0,9395 | 0,9449 | +0,0054 |
| AUC | 0,9977 | 0,9977 | +0,0000 |
| Recall DoS | 0,9932 | 0,9932 | +0,0000 |
| Recall MitM | 0,9676 | 0,9760 | +0,0085 |
| Recall intrusion | 0,9789 | 0,9737 | −0,0053 |
| FP normal | 4,4377 % | 4,0035 % | −0,4342 pp |

#### XGBoost (frames con ventana)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9798 | 0,9825 | +0,0027 |
| Macro-F1 | 0,9563 | 0,9622 | +0,0060 |
| AUC | 0,9991 | 0,9991 | +0,0000 |
| FP normal | 3,3802 % | 2,8893 % | −0,4909 pp |

#### LSTM

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9245 | 0,9317 | +0,0072 |
| Macro-F1 | 0,9198 | 0,9244 | +0,0046 |
| AUC | 0,9455 | 0,9493 | +0,0038 |
| Recall DoS (cond.) | 0,9664 | 0,9849 | +0,0185 |
| Recall MitM (cond.) | 0,0347 | 0,0295 | −0,0052 |
| Recall intrusion (cond.) | 0,7222 | 0,7222 | +0,0000 |
| FP normal | 3,5907 % | 3,6175 % | +0,0268 pp |

#### Híbrido LSTM + XGBoost

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9865 | 0,9847 | −0,0018 |
| Macro-F1 | 0,9732 | 0,9682 | −0,0051 |
| AUC | 0,9982 | 0,9984 | +0,0002 |
| Recall DoS | 0,9953 | 0,9953 | +0,0000 |
| Recall MitM | 0,9636 | 0,9723 | +0,0087 |
| Recall intrusion | 0,6667 | 0,7222 | +0,0556 |
| FP normal | 1,9370 % | 2,3717 % | +0,4347 pp |

### Recall por tipo (Fase 3.1)

| Modelo | Tipo | Frames test | Evaluables | Detectados | Recall cond. | Recall e2e test |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | DoS | 9.103 | 9.103 | 9.041 | 0,9932 | 0,9932 |
| XGBoost | MitM | 709 | 709 | 692 | 0,9760 | 0,9760 |
| XGBoost | intrusion | 380 | 380 | 370 | 0,9737 | 0,9737 |
| LSTM | DoS | 9.103 | 7.466 | 7.353 | 0,9849 | 0,8078 |
| LSTM | MitM | 709 | 577 | 17 | 0,0295 | 0,0240 |
| LSTM | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |
| Híbrido | DoS | 9.103 | 7.466 | 7.431 | 0,9953 | 0,8163 |
| Híbrido | MitM | 709 | 577 | 561 | 0,9723 | 0,7913 |
| Híbrido | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |

### Interpretación

- El efecto es pequeño y mixto. XGBoost y LSTM mejoran balanced accuracy y
  macro-F1 y **bajan el FP de normal** (XGBoost −0,43 pp); el híbrido empeora
  balanced accuracy y macro-F1 y **sube el FP de normal** (+0,43 pp).
- El recall de DoS del LSTM sube (+0,0185) y el de MitM del híbrido también
  (+0,0087), pero MitM del LSTM baja (−0,0052). El recall de intrusion del
  XGBoost baja levemente (0,9789 → 0,9737, 2 frames menos).
- La cobertura de estas features está confundida con “ser una sesión TCP MQTT”;
  no se interpreta como detección directa de ataque. No se afirma mejora global.

## 3.2 Nota sobre `_connection`

`_connection` es una **aproximación de sesión/conexión** construida por el
pipeline: mismos endpoints `IP:puerto` más un contador acumulado de CONNECT. No
es necesariamente una conexión TCP real reconstruida con `tcp.stream`, SYN y
FIN. El dataset no incluye `tcp.stream`; el agente de despliegue correlaciona
por el `tcp.stream` de tshark. Por tanto, el contexto de CONNECT propagado en
entrenamiento (por `_connection`) y en despliegue (por `tcp.stream`) son
equivalentes en intención pero no idénticos en el mecanismo.

La nota quedó en el notebook (sección 3, “Nota sobre `_connection` (Fase 3.2)”)
y en `pipeline_config.json` dentro de `stream_state.connect_context`.

## 3.3 Contexto por origen (Etapa 2)

### Objetivo y semántica

Añadir, por origen, el comportamiento reciente: frames/s, bytes/s, conexiones
recientes y CONNECTs recientes. Reglas fijadas por diseño:

- Ventana de **5 s**, clave única `ip.src`. Sin `ip.src` → features **NaN**
  (imputación), no 0.
- La ventana contiene **frames anteriores en el orden del stream** con
  `frame.time_epoch` dentro de los últimos 5 s; el frame actual **no** entra en
  sus propias estadísticas. Frames con el mismo timestamp pero anteriores en el
  orden sí cuentan.
- Tasas divididas entre el `N` fijo. Con clave presente pero sin historial → **0**.
- Offline por partición, con estado **reiniciado al inicio de cada partición** y
  ante retroceso del reloj; online el estado es continuo (se documenta la brecha).

### Implementación

Notebook: `ORIGIN_CONTEXT`, `ORIGIN_CONTEXT_WINDOW_SECONDS = 5.0` y
`build_origin_context(df, partitions, 5.0)`. Las 4 features entran en Etapa 2
(`FEATURE_COLUMNS` pasa a 22). El escalado del LSTM se vuelve tolerante a NaN
(media de train → relleno → escalado → 0 en posiciones imputadas), necesario para
estas features.

Infraestructura: `ContextFeatureSource` (nuevo `infrastructure/features/`), un
decorador de `FeatureSource` que mantiene solo estado causal por `ip.src` y
`ctx_origen_*` por fila; `TsharkFeatureSource` deja de mantener ventanas
temporales. `_common.add_stage2_features` mapea los transportes a features;
`composition_root` cablea el builder. `pipeline_config.json` declara
`stream_state.origin_context`.

### Cobertura (IP presente / con historial)

| Partición | Clase | Frames | Con `ip.src` | Con historial |
| --- | --- | ---: | ---: | ---: |
| train | DoS | 27.309 | 99,95 % | 99,84 % |
| train | intrusion | 1.139 | 99,82 % | 96,75 % |
| train | mitm | 2.126 | 14,06 % | 13,73 % |
| train | normal | 140.952 | 95,78 % | 91,70 % |
| val | DoS | 9.102 | 99,98 % | 99,71 % |
| val | intrusion | 379 | 100,00 % | 88,39 % |
| val | mitm | 1.020 | 0,00 % | 0,00 % |
| val | normal | 46.983 | 96,15 % | 90,65 % |
| test | DoS | 9.103 | 99,93 % | 99,73 % |
| test | intrusion | 380 | 100,00 % | 86,32 % |
| test | mitm | 709 | 11,71 % | 11,14 % |
| test | normal | 46.984 | 96,16 % | 90,12 % |

Por observación (test): TCP 100 % con IP; L2 49,92 %. Como MitM es L2, sus
features de origen son NaN: la señal no lo cubre y queda para 3.4.

### Antes → después

“Antes” = contexto de CONNECT (sección 3.1, `tmp/fase3/diagnostics.json`
original, valores en este reporte). “Después” = `tmp/fase3/step33/diagnostics.json`.

#### XGBoost (todos los frames)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9756 | 0,9805 | +0,0049 |
| Macro-F1 | 0,9449 | 0,9573 | +0,0124 |
| AUC | 0,9977 | 0,9982 | +0,0005 |
| Recall DoS | 0,9932 | 0,9934 | +0,0002 |
| Recall MitM | 0,9760 | 0,9676 | −0,0084 |
| Recall intrusion | 0,9737 | 0,9789 | +0,0052 |
| FP normal | 4,0035 % | 3,0010 % | **−1,0025 pp** |

#### XGBoost (frames con ventana)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9825 | 0,9890 | +0,0065 |
| Macro-F1 | 0,9622 | 0,9779 | +0,0157 |
| AUC | 0,9991 | 0,9993 | +0,0002 |
| FP normal | 2,8893 % | 1,5940 % | **−1,2953 pp** |

#### LSTM

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9317 | 0,9315 | −0,0002 |
| Macro-F1 | 0,9244 | 0,9252 | +0,0008 |
| AUC | 0,9493 | 0,9470 | −0,0023 |
| Recall DoS (cond.) | 0,9849 | 0,9849 | +0,0000 |
| Recall MitM (cond.) | 0,0295 | 0,0260 | −0,0035 |
| Recall intrusion (cond.) | 0,7222 | 0,7222 | +0,0000 |
| FP normal | 3,6175 % | 3,5102 % | −0,1073 pp |

#### Híbrido LSTM + XGBoost

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9847 | 0,9884 | +0,0037 |
| Macro-F1 | 0,9682 | 0,9806 | +0,0124 |
| AUC | 0,9984 | 0,9990 | +0,0006 |
| Recall DoS | 0,9953 | 0,9949 | −0,0004 |
| Recall MitM | 0,9723 | 0,9324 | −0,0399 |
| Recall intrusion | 0,7222 | 0,5556 | −0,1666 |
| FP normal | 2,3717 % | 1,2687 % | **−1,1030 pp** |

### Recall por tipo (3.3)

| Modelo | Tipo | Frames test | Evaluables | Detectados | Recall cond. | Recall e2e test |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | DoS | 9.103 | 9.103 | 9.042 | 0,9934 | 0,9934 |
| XGBoost | MitM | 709 | 709 | 686 | 0,9676 | 0,9676 |
| XGBoost | intrusion | 380 | 380 | 372 | 0,9789 | 0,9789 |
| LSTM | DoS | 9.103 | 7.466 | 7.353 | 0,9849 | 0,8078 |
| LSTM | MitM | 709 | 577 | 15 | 0,0260 | 0,0212 |
| LSTM | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |
| Híbrido | DoS | 9.103 | 7.466 | 7.428 | 0,9949 | 0,8160 |
| Híbrido | MitM | 709 | 577 | 538 | 0,9324 | 0,7588 |
| Híbrido | intrusion | 380 | 18 | 10 | 0,5556 | 0,0263 |

### Interpretación e impacto en MitM/intrusion

- La población de frames **no cambia** (no se descarta ninguno). Lo que cambia es
  la disponibilidad de features: intrusion (TCP) recibe las 4 de origen; MitM
  (L2, `ip.src` nulo en el 88 %) las recibe como NaN y no se ve cubierto.
- **Baja fuerte del FP de normal** en XGBoost (−1,00 pp), XGBoost con ventana
  (−1,30 pp) e híbrido (−1,10 pp), con subida de balanced accuracy y macro-F1.
- El recall de intrusion del XGBoost sube (+0,0052) y el de MitM baja (−0,0084).
  En el híbrido, intrusion cae 0,7222 → 0,5556 sobre **18 ventanas** (10 de 18
  detectadas), no concluyente; MitM del híbrido baja 0,9723 → 0,9324.
- El LSTM queda casi plano (AUC −0,0023).
- No se afirma mejora global: la caída de FP coexiste con menos recall de MitM en
  el híbrido y menos intrusion en el XGBoost de híbrido.

## 3.4 Features L2 (Etapa 2)

### Objetivo y semántica

`fe_is_broadcast` (`eth.dst == ff:ff:ff:ff:ff:ff`) y `fe_is_multicast` (bit
multicast de `eth.dst`) por frame, más tres tasas causales de 5 s **por
`eth.src`** para todos los frames (sin fallback ni mezcla con `eth.dst`):
`fe_l2_frames_s`, `fe_l2_broadcasts` y `fe_l2_burst_ratio` (fracción de deltas
consecutivos `< 100 µs`). El par `(eth.src, eth.dst)` se usó solo para agrupar
episodios L2. Misma semántica causal que 3.3 (frames anteriores, frame actual
excluido, tasas entre 5, 0 sin historial, NaN sin `eth.src`). El par se documenta
como contexto L2; no se afirma detección de ARP spoofing.

### Implementación

Notebook: `L2_CONTEXT`, `build_l2_context` y las 5 features en Etapa 2
(`FEATURE_COLUMNS` pasa a 27). Infra: `ContextFeatureSource` mantiene ahora
también el estado por `eth.src`; `_common.L2_CONTEXT`, `tshark_schema` y
`pipeline_config.stream_state.l2_context` actualizados.

### Broadcast / multicast en test

| Clase | Frames | Broadcast | Multicast | Con `eth.src` |
| --- | ---: | ---: | ---: | ---: |
| DoS | 9.103 | 0 | 0 | 9.103 |
| intrusion | 380 | 0 | 0 | 380 |
| mitm | 709 | 510 | 511 | 709 |
| normal | 46.984 | 22 | 495 | 46.984 |

En todo el dataset hay solo 11 `eth.src` distintos. El broadcast/multicast se
concentra en MitM-L2.

### Antes → después

“Antes” = 3.3 (`tmp/fase3/step33/diagnostics.json`). “Después” =
`tmp/fase3/step34/diagnostics.json`.

#### XGBoost (todos los frames)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9805 | 0,9815 | +0,0010 |
| Macro-F1 | 0,9573 | 0,9589 | +0,0016 |
| AUC | 0,9982 | 0,9984 | +0,0002 |
| Recall DoS | 0,9934 | 0,9934 | +0,0000 |
| Recall MitM | 0,9676 | 0,9803 | +0,0127 |
| Recall intrusion | 0,9789 | 0,9789 | +0,0000 |
| FP normal | 3,0010 % | 2,9010 % | −0,1000 pp |

#### XGBoost (frames con ventana)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9890 | 0,9896 | +0,0006 |
| Macro-F1 | 0,9779 | 0,9783 | +0,0004 |
| AUC | 0,9993 | 0,9994 | +0,0001 |
| FP normal | 1,5940 % | 1,5969 % | +0,0029 pp |

#### LSTM

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9315 | 0,9608 | **+0,0293** |
| Macro-F1 | 0,9252 | 0,9427 | +0,0175 |
| AUC | 0,9470 | 0,9714 | **+0,0244** |
| Recall DoS (cond.) | 0,9849 | 0,9849 | +0,0000 |
| Recall MitM (cond.) | 0,0260 | 0,8943 | **+0,8683** |
| Recall intrusion (cond.) | 0,7222 | 0,7222 | +0,0000 |
| FP normal | 3,5102 % | 3,7129 % | +0,2027 pp |

#### Híbrido LSTM + XGBoost

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9884 | 0,9890 | +0,0006 |
| Macro-F1 | 0,9806 | 0,9816 | +0,0010 |
| AUC | 0,9990 | 0,9982 | −0,0008 |
| Recall DoS | 0,9949 | 0,9946 | −0,0003 |
| Recall MitM | 0,9324 | 0,9497 | +0,0173 |
| Recall intrusion | 0,5556 | 0,3333 | −0,2223 |
| FP normal | 1,2687 % | 1,1977 % | −0,0710 pp |

### Recall por tipo (3.4)

| Modelo | Tipo | Frames test | Evaluables | Detectados | Recall cond. | Recall e2e test |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | DoS | 9.103 | 9.103 | 9.043 | 0,9934 | 0,9934 |
| XGBoost | MitM | 709 | 709 | 695 | 0,9803 | 0,9803 |
| XGBoost | intrusion | 380 | 380 | 372 | 0,9789 | 0,9789 |
| LSTM | DoS | 9.103 | 7.466 | 7.353 | 0,9849 | 0,8078 |
| LSTM | MitM | 709 | 577 | 516 | 0,8943 | 0,7278 |
| LSTM | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |
| Híbrido | DoS | 9.103 | 7.466 | 7.425 | 0,9946 | 0,8158 |
| Híbrido | MitM | 709 | 577 | 548 | 0,9497 | 0,7729 |
| Híbrido | intrusion | 380 | 18 | 6 | 0,3333 | 0,0158 |

### Interpretación e impacto en MitM/intrusion

- **MitM mejora de forma marcada en el LSTM**: recall condicionado 0,0260 →
  0,8943 y AUC 0,9470 → 0,9714, sin cambiar el recall de intrusion y con +0,20 pp
  de FP de normal. Es el efecto más grande observado hasta ahora, coherente con
  que MitM es tráfico L2 con broadcast/multicast.
- XGBoost también sube algo el recall de MitM (+0,0127) y baja el FP normal.
- **Intrusion del híbrido cae** 0,5556 → 0,3333 sobre 18 ventanas (6 de 18
  detectadas); no concluyente por el tamaño, pero se reporta.
- La población de frames no cambia; lo que cambia es que MitM-L2 deja de quedar
  sin contexto (3.3 le daba NaN) y recibe features L2.

## 3.5 Decodificación de `mqtt.hdrflags`, wildcard y novedad de tópico

### Implementación

`mqtt.hdrflags` crudo **se reemplaza** por `fe_mqtt_type`, `fe_mqtt_qos`,
`fe_mqtt_dup` y `fe_mqtt_retain` (decodificación determinista, verificada:
`type == mqtt.msgtype` en 47.972/47.972). Se añade `fe_topic_wildcard` (Etapa 1)
y `fe_topic_novedad` (Etapa 2) con el artefacto `known_topics.json` aprendido
**solo de train** (3.522 tópicos). `FEATURE_COLUMNS` pasa a 32. Los campos no
observables quedan NaN.

### Decodificados y wildcard (test)

| Clase | Con `hdrflags` | Tópico presente | Tópico novedoso | Wildcard |
| --- | ---: | ---: | ---: | ---: |
| DoS | 7.770 | 7.381 | 7.381 | 0 |
| intrusion | 166 | 63 | 0 | 0 |
| mitm | 13 | 13 | 0 | 0 |
| normal | 1.790 | 740 | 0 | 1 |

`fe_topic_wildcard` es prácticamente constante (un único frame en test); se
incluye pero se reporta su variabilidad.

### Antes → después (Antes = 3.4)

| Modelo | Bal. acc. | Macro-F1 | AUC | FP normal | Recall MitM | Recall intrusion |
| --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 0,9815→0,9812 | 0,9589→0,9580 | 0,9984 | 2,9010→2,9648 % | 0,9803→0,9760 | 0,9789 (0) |
| XGBoost (ventana) | 0,9896→0,9895 | 0,9783→0,9782 | 0,9994 | 1,5969→1,5940 % | N/A | N/A |
| LSTM | 0,9608→0,9584 | 0,9427→0,9373 | 0,9714→0,9727 | 3,7129→4,1867 % | 0,8943→0,8891 | 0,7222 (0) |
| Híbrido | 0,9890→0,9884 | 0,9816→0,9800 | 0,9982→0,9986 | 1,1977→1,3249 % | 0,9497→0,9567 | 0,3333 (0) |

### Interpretación

Cambios pequeños y mixtos: el AUC del LSTM sube (+0,0013) y el híbrido mejora
MitM (+0,0070), pero el FP de normal sube en LSTM (+0,47 pp) e híbrido (+0,13 pp)
y el recall de intrusion del híbrido sigue en 0,3333 (6/18 ventanas). No se
afirma mejora. `fe_topic_wildcard` no aporta variabilidad en estos datos.

## 3.6 Faltantes (política mínima)

### Implementación

`fe_has_mqtt` = 1 si `mqtt.hdrflags` no está vacío, 0 si no (Etapa 1). Se amplía
`NAN_FEATURES` a todas las features no observables (`mqtt.len`, `mqtt.topic_len`,
decodificadas, entropías, profundidad, ratio y contexto de CONNECT). XGBoost
conserva **NaN**; el LSTM usa la media de train para escalar y fija **0** en las
posiciones imputadas, con `fe_has_mqtt` como indicador. `pipeline_config.json`
declara `nan_policy` y sus columnas. `FEATURE_COLUMNS` pasa a 33.

### Consistencia de `fe_has_mqtt`

Fila a fila sobre las 286.186 tramas: 0 desacuerdos con `mqtt.hdrflags`, 0 con
`mqtt.msgtype` y 0 con `mqtt.len`.

### Antes → después (Antes = 3.5)

| Modelo | Bal. acc. | Macro-F1 | AUC | FP normal | Recall DoS | Recall MitM | Recall intrusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 0,9812 | 0,9580→0,9584 | 0,9984 | 2,9648→2,9265 % | 0,9938 | 0,9760→0,9774 | 0,9789→0,9658 |
| XGBoost (ventana) | 0,9895→0,9893 | 0,9782→0,9783 | 0,9994 | 1,5940→1,5762 % | N/A | N/A | N/A |
| LSTM | **0,9584→0,5408** | **0,9373→0,5362** | **0,9727→0,9207** | 4,1867→4,3267 % | **0,9849→0,0557** | 0,8891→0,8925 | 0,7222 (0) |
| Híbrido | 0,9884→0,9890 | 0,9800→0,9816 | 0,9986→0,9985 | 1,3249→1,2036 % | 0,9940 | 0,9567 (0) | 0,3333→0,4444 |

### Interpretación

- **El LSTM se degrada con fuerza**: balanced accuracy 0,958 → 0,541, Macro-F1
  0,937 → 0,536, AUC 0,973 → 0,921 y recall de DoS 0,985 → 0,056. Al pasar a NaN
  varias columnas y reemplazarlas por 0 tras el escalado, el autoencoder pierde
  la señal de los frames no MQTT, que son la mayoría.
- XGBoost e híbrido se mantienen estables; el híbrido mejora algo (intrusion
  0,333 → 0,444; FP 1,32 → 1,20 %) porque su segundo nivel sigue usando XGBoost
  con NaN nativos.
- No se afirma mejora global: la política mínima es correcta para XGBoost, pero
  degrada el LSTM y debe tratarse antes de la Fase 4 (donde el AUC del LSTM es el
  criterio).

## Resumen de la Fase 3

- **Features nuevas (14):** 4 de contexto de CONNECT (`fe_mqtt_ver`, `fe_mqtt_kalive`,
  `fe_mqtt_cleansess`, `fe_mqtt_clientid_len`); 4 de contexto por origen; 5 de L2;
  `fe_mqtt_type/qos/dup/retain` (reemplazan `mqtt.hdrflags`), `fe_topic_wildcard`
  y `fe_topic_novedad`. Total: **33 features** (22 de Etapa 1 + 11 de Etapa 2).
- **Artefactos nuevos:** `known_topics.json`; `ContextFeatureSource` con estado
  causal por `ip.src` y `eth.src` (ventana 5 s); `pipeline_config` documenta
  `feature_stages`, `stream_state` y `nan_policy`.
- **Tests:** 43 pruebas (42 correctas, 1 omitida por tshark) y `validate_notebook`
  OK (paridad de features y tres adaptadores).
- **Problema principal:** la política NaN mínima de 3.6 degrada el LSTM
  (bal. acc. 0,96 → 0,54). No se corrigió; queda para revisión antes de la Fase 4.
- **Impacto en MitM/intrusion:** MitM se beneficia de lasfeatures L2 (LSTM recall
  0,026 → 0,89 en 3.4); intrusion queda con muy pocas ventanas evaluables (18) y
  el híbrido oscila 0,33–0,72 según la sub-fase. La población de frames no cambió.
- **No se actualizaron** los artefactos de `./modelos_agente/`; siguen en 13
  features e inconsistentes con el código (restricción 7).



## Qué se ejecutó

- Notebook completo sobre los tres CSV reales, 100 árboles y 10 épocas, en CPU,
  sin errores.
- Fase 3.1 en notebook e infraestructura; tests de CONNECT añadidos.
- Diagnóstico del contexto de CONNECT (cobertura por partición/clase/observación
  y comprobación de reconstrucción causal) en `tmp/fase3/diagnostics.json`.
- Fase 3.3 en notebook (`build_origin_context`), infraestructura
  (`ContextFeatureSource`, `add_stage2_features`) y `composition_root`; tests del
  builder causal añadidos.
- Diagnóstico de 3.3 (cobertura de origen por partición/clase/observación) en
  `tmp/fase3/step33/diagnostics.json`.
- Fase 3.4 en notebook (`build_l2_context`) y en `ContextFeatureSource` (estado
  por `eth.src`); diagnóstico de L2 en `tmp/fase3/step34/diagnostics.json`.
- Fase 3.5 en notebook e infraestructura (`mqtt.hdrflags` decodificado,
  `fe_topic_wildcard`, `known_topics.json`, `fe_topic_novedad`); diagnóstico en
  `tmp/fase3/step35/diagnostics.json`.
- Fase 3.6 en notebook e infraestructura (`fe_has_mqtt`, `NAN_FEATURES`,
  `nan_policy`); diagnóstico en `tmp/fase3/step36/diagnostics.json`.
- `tests.test_context_builder`: 9 pruebas; `tests.test_mqtt_features`: 5 pruebas.
- `tests/validate_notebook.py`: paridad de features, separación de ventanas y
  carga de los tres adaptadores, **OK**.
- Suite `python -m unittest discover -s tests -v`: 43 pruebas, 42 correctas y 1
  omitida (tshark no instalado).
- Entorno: Python 3.11.16, NumPy 2.4.6, pandas 3.0.5, XGBoost 3.2.0,
  PyTorch 2.14.0+cu130 sobre CPU.

Archivos reproducibles:

- `tmp/fase3/ml-mqtt-model-fase3.ipynb` / `-executed.ipynb` (3.1, 18 features);
- `tmp/fase3/step33/` (3.3, 22 features), `tmp/fase3/step34/` (3.4, 27 features),
  `tmp/fase3/step35/` (3.5, 32 features) y `tmp/fase3/step36/` (3.6, 33 features),
  cada uno con su notebook, `diagnostics.json` y `modelos_agente/`.

## Qué no se ejecutó

- **No se actualizaron los artefactos de `./modelos_agente/`.** Siguen en 13
  features sin `known_origins.json` ni `known_topics.json`, y el código ya espera
  33 features más los artefactos: el conjunto versionado está **inconsistente**
  (restricción 7).
- No se ejecutó tráfico real, broker ni MQTTS.
- No se hizo rotación de folds ni split temporal/episódico (Fase 5).

## Qué continúa sin verificar

- Que el forward-fill por `tcp.stream` en despliegue coincida con el de
  `_connection` en entrenamiento sobre tráfico real.
- Si la cobertura diferencial de `fe_mqtt_*` (intrusion/DoS vs MitM/normal)
  aporta señal propia o solo refleja “sesión TCP MQTT”.
- Paridad exacta entre `ContextFeatureSource` (continuo) y `build_origin_context`
  / `build_l2_context` (por partición): la brecha de partición no se midió en
  tráfico real.
- Generalización de MitM en validation (2 grupos) e intrusion (18 ventanas
  evaluables).
- El resto de features de contexto causal (3.5–3.6).
