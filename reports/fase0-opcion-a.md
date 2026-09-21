# Fase 0 — opción A: población TCP + L2

Fecha de ejecución: 2026-09-21.

Tras elegir la opción A se amplió la observación a todos los frames Ethernet con
`frame.time_epoch`, se definió una agrupación causal para L2 y se volvió a medir
la línea base antes de iniciar la Fase 1. No se añadieron features L2 específicas
ni pesos por tipo de ataque.

## Población y agrupación

- TCP: misma aproximación anterior por endpoints y contador acumulado de CONNECT.
- L2: par MAC **no dirigido** para identificar el flujo bidireccional.
- Episodio L2: comienza con el primer frame del par, tras un gap estrictamente
  mayor que 1 segundo o ante un retroceso del reloj.
- Ventana L2: siempre direccional, `eth.src → eth.dst`.
- El reloj y las MAC solo mantienen estado; no entran como features del modelo.

El umbral de 1 segundo es causal y reproducible en streaming. En el análisis
previo produjo 253 grupos con frames MitM; tras construir grupos que pueden
contener más de una clase quedaron 244 episodios L2 que contienen MitM. No se
eligió usando rendimiento del modelo.

Los 286.186 frames tienen MAC origen/destino y reloj, por lo que no se descarta
ninguno:

| Captura | Clase | Frames | TCP | L2 | Grupos TCP | Episodios L2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DoS | normal | 49.111 | 43.000 | 6.111 | 697 | 441 |
| DoS | DoS | 45.514 | 45.460 | 54 | 907 | 26 |
| MitM | normal | 106.813 | 99.134 | 7.679 | 864 | 3.506 |
| MitM | mitm | 3.855 | 380 | **3.475** | 7 | **244** |
| Intrusion | normal | 78.995 | 69.863 | 9.132 | 2.127 | 2.215 |
| Intrusion | intrusion | 1.898 | 1.894 | 4 | 414 | 3 |

Esto recupera los 3.475 frames MitM que el filtro IPv4/TCP descartaba. No prueba
suplantación IP↔MAC ni identifica ARP: el CSV no contiene los campos necesarios.

## Nueva partición

Se conservaron semilla 42, `StratifiedGroupKFold` de cinco folds y la primera
combinación con cobertura de clases: test fold 1, validation fold 2 y train folds
3–5. La población cambió, por lo que esta partición no es la misma que la línea
base IPv4/TCP.

| Partición | Frames | TCP | L2 | Grupos TCP | Episodios L2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 171.526 | 155.407 | 16.119 | 2.812 | 3.878 |
| validation | 57.484 | 52.016 | 5.468 | 937 | 1.239 |
| test | 57.176 | 52.308 | 4.868 | 941 | 1.302 |

| Partición | Clase | Frames | Grupos que contienen la clase |
| --- | --- | ---: | ---: |
| train | DoS | 27.309 | 556 |
| train | mitm | 2.126 | 177 |
| train | intrusion | 1.139 | 254 |
| train | normal | 140.952 | 5.909 |
| validation | DoS | 9.102 | 188 |
| validation | mitm | 1.020 | **2** |
| validation | intrusion | 379 | 80 |
| validation | normal | 46.983 | 1.969 |
| test | DoS | 9.103 | 189 |
| test | mitm | 709 | **72** |
| test | intrusion | 380 | 83 |
| test | normal | 46.984 | 1.972 |

Un grupo puede contener más de una clase. La independencia de MitM en test
mejora de 1 a 72 grupos, aunque validation sigue concentrada en solo 2 grupos.

## Línea base medida con opción A

| Modelo | Frames | Bal. acc. | Macro-F1 | AUC | FP normal |
| --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost (todos) | 57.176 | 0,9834 | 0,9766 | 0,9981 | 1,2408 % |
| XGBoost (con ventana) | 41.876 | 0,9904 | 0,9898 | 0,9991 | 0,4288 % |
| LSTM | 41.876 | 0,9252 | 0,9213 | 0,9259 | 3,4506 % |
| Híbrido | 41.876 | 0,9915 | 0,9917 | 0,9989 | 0,3046 % |

El umbral LSTM, calibrado solo con ventanas normales de validation, fue
`1,478196144104004`.

### Referencia descriptiva frente a IPv4/TCP

| Modelo | Bal. acc. IPv4/TCP → TCP+L2 | Macro-F1 IPv4/TCP → TCP+L2 | AUC IPv4/TCP → TCP+L2 |
| --- | ---: | ---: | ---: |
| XGBoost (todos) | 0,9886 → 0,9834 | 0,9817 → 0,9766 | 0,9994 → 0,9981 |
| XGBoost (con ventana) | 0,9912 → 0,9904 | 0,9889 → 0,9898 | 0,9997 → 0,9991 |
| LSTM | 0,9561 → 0,9252 | 0,9386 → 0,9213 | 0,9723 → 0,9259 |
| Híbrido | 0,9929 → 0,9915 | 0,9923 → 0,9917 | 0,9995 → 0,9989 |

Esta tabla **no es un antes/después causal**: la población, los grupos y las
particiones cambiaron por exigencia de la opción A. No se usa para afirmar una
mejora global.

## Recall por tipo

| Modelo | Tipo | Frames test | Evaluables | Detectados | Recall condicionado | Recall e2e test |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | DoS | 9.103 | 9.103 | 9.035 | 0,9925 | 0,9925 |
| XGBoost | MitM | 709 | 709 | 577 | **0,8138** | **0,8138** |
| XGBoost | intrusion | 380 | 380 | 368 | 0,9684 | 0,9684 |
| LSTM | DoS | 9.103 | 7.466 | 7.215 | 0,9664 | 0,7926 |
| LSTM | MitM | 709 | 577 | 19 | **0,0329** | **0,0268** |
| LSTM | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |
| Híbrido | DoS | 9.103 | 7.466 | 7.429 | 0,9950 | 0,8161 |
| Híbrido | MitM | 709 | 577 | 513 | **0,8891** | **0,7236** |
| Híbrido | intrusion | 380 | 18 | 7 | 0,3889 | 0,0184 |

Para XGBoost cada frame es evaluable. Para LSTM e híbrido, el recall e2e usa
todos los frames de ataque de test como denominador y considera no detectados
los frames que no terminan una ventana completa. LSTM conserva etiqueta binaria
`any-in-window`; el tipo siempre proviene de la última fila. El híbrido usa
`last-frame`.

La opción A permite medir un recall e2e test real porque todos los frames tienen
grupo y partición. Los resultados son mixtos: XGBoost e híbrido detectan muchos
más frames MitM observables, pero el LSTM aislado cae fuertemente. Intrusion
continúa con cobertura de ventanas muy baja (18 de 380 frames de test).

## Contrato de despliegue

`pipeline_config.json` ahora declara:

- `capture_filter: ""`;
- `observation_mode: ethernet_tcp_and_l2`;
- `l2_episode_gap_seconds: 1.0`;
- claves de estado para ventanas TCP y episodios/direcciones L2;
- `split_strategy: tcp_connection_or_l2_episode_grouped_train_val_test`.

`evaluation_split.json` registra la selección Ethernet, las 286.186 filas y la
nueva partición. `FrameContext` transporta MAC origen/destino, pero
`tshark_schema.FEATURE_COLUMNS` las excluye de la matriz del modelo. El agente
reinicia causalmente ambos buffers direccionales del par MAC al cambiar de
episodio.

Los ocho artefactos se reexportaron y reemplazaron juntos en `modelos_agente/`.
No se mezclaron modelos, scaler o configuración de versiones distintas.

## Qué se ejecutó

- Notebook completo sobre los tres CSV reales, 100 árboles y 10 épocas.
- XGBoost, LSTM, híbrido y XGBoost restringido a frames con ventana.
- Suite de 27 tests: 26 pasaron y 1 se omitió porque tshark no está instalado en
  el contenedor ML.
- Preparación del notebook con datos reales.
- Smoke de entrenamiento/exportación con 5 árboles y 1 época.
- Carga de los tres adapters contra los artefactos completos y predicción sobre
  una ventana L2.
- `py_compile` sobre los módulos modificados.

## Qué no se ejecutó

- No se ejecutó tráfico real ni un broker.
- No se añadieron todavía `fe_is_broadcast`, `fe_is_multicast` ni tasas L2; eso
  corresponde a la Fase 3.4.
- No se aplicaron los pesos por cuatro clases de la Fase 1.
- No se hizo rotación de cinco folds ni split temporal/episódico de la Fase 5.

## Qué continúa sin verificar

- Generalización de MitM en validation, que solo contiene 2 grupos con esa clase.
- Sensibilidad del resultado al umbral causal de episodio L2 de 1 segundo.
- Mecanismo exacto del etiquetado MitM; no se afirma detección de ARP spoofing.
- Desempeño de despliegue sobre MQTTS y capturas independientes.
- La comparación justa de fases futuras debe usar esta nueva población y esta
  misma partición, no la línea base IPv4/TCP.
