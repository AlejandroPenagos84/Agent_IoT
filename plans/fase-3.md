# Fase 3 — Refinar contexto causal, L2 y preprocesado

Leer primero [README.md](README.md). 3.1–3.6 ya tienen código; refinarlo, no duplicarlo.

## Problemas observados

- Notebook con 33 features frente a artefactos principales de 13: actualización final
  pendiente por decisión del usuario, no tarea de esta fase.
- Notebook imputa antes de escalar y fija 0 tras el escalado; adapters LSTM/híbrido
  llaman directamente `scaler.transform(raw)`, sin reproducir todo el tratamiento.
- `reports/fase3.md` registra degradación fuerte en 3.6. La explicación del reporte
  es una hipótesis que se debe contrastar; no asumir causalidad demostrada.
- El validador reutiliza columnas de contexto offline, por lo que no comprueba todo
  el recorrido de `TsharkFeatureSource` y `ContextFeatureSource`.

## Archivos

Notebook; `infrastructure/features/context_builder.py`; fuentes y schema de tshark;
`infrastructure/classifiers/{_common,anomaly,hybrid,_frame}.py`; `composition_root.py`;
`application/use_cases/agent.py`; pruebas existentes de features, contexto y ventanas.

## 3.1 CONNECT

- Actualizar contexto solo en frames identificados como CONNECT; propagar hacia
  adelante dentro de la misma conexión. No backward-fill ni datos de otra conexión.
- Sin CONNECT capturado, conservar faltantes. Un CONNECT nuevo reinicia el contexto
  de sesión correspondiente; un campo ausente no debe heredar otra sesión.
- Offline usar la aproximación de conexión del notebook; online `tcp.stream`.
  Documentar que son mecanismos distintos y escribir casos equivalentes comprobables.

## 3.2 Ciclo de vida y agrupación

- Aplicar las reglas de admisión, normalización y episodios de fase 0.
- Reiniciar estados de identidad, CONNECT, contexto y ventanas ante nueva captura,
  truncado/rotación del JSONL o retroceso de reloj. Escribir una señal explícita de
  reinicio entre adapters y caso de uso si hace falta; no importar adapters en Agent.
- No reiniciar contexto por origen de 5 s por cada episodio L2 de 1 s: son estados
  diferentes. Los límites de captura/partición sí reinician ambos.
- Expirar claves inactivas y sus buffers para que el estado no crezca indefinidamente;
  documentar límites de retención y aplicar la misma política a los replays de paridad.

## 3.3 Contexto por origen

Ventana fija de 5 s, por `ip.src`. Para un frame a tiempo `t`, usar frames anteriores
en orden estable con timestamp en `[t-5, t]`; excluir el frame actual. Los anteriores
con igual timestamp sí cuentan. Calcular frames/5, bytes/5, conexiones distintas y
CONNECTs. Clave presente sin historial → 0; clave ausente → NaN.

Offline procesar por captura/segmento y partición, en orden temporal estable. No
depender de ordenar índices de un DataFrame que mezcla capturas. Online usar igual
semántica sobre el flujo recibido. Documentar el menor contexto offline debido al split.

## 3.4 L2

- `fe_is_broadcast`: MAC destino normalizada igual a `ff:ff:ff:ff:ff:ff`.
- `fe_is_multicast`: bit menos significativo del primer octeto. Broadcast también
  tiene indicador multicast=1; no hacerlos mutuamente excluyentes.
- Destino ausente/inválido → indicadores NaN; no interpretarlo como unicast válido.
- Tasas por **MAC origen**, sobre todos los frames Ethernet admitidos, incluidos TCP.
  No calcularlas por par MAC ni limitar el historial a `_observation='l2'`.
- Misma ventana de 5 s y exclusión del frame actual que 3.3. `frames_s=count/5`,
  `broadcasts=count_broadcast`; `burst_ratio` = proporción de deltas entre eventos
  consecutivos del historial que cumplen `0 <= delta < 100e-6` segundos.
- Menos de dos eventos históricos → burst ratio 0. Sin origen válido → tasas NaN.
- Las MAC crudas no llegan al clasificador. No afirmar detección directa de ARP spoofing.

## 3.5 MQTT y topics

- Alinear decodificación decimal/hexadecimal de `hdrflags` y validar rango de byte.
  Conservar la selección de primera ocurrencia del capturador; aplicar la misma regla
  explícita a valores múltiples del CSV. Añadir contador diagnóstico de esos casos.
- Distinguir MQTT ausente de cabecera presente pero inválida; no convertir una
  cabecera inválida en una clase o en tipo MQTT válido por truncamiento de bits.
- `known_topics` se aprende solo de train, con strip de espacios, sin cambiar case.
  Tópico presente y desconocido → novedad 1; conocido → 0; ausente → NaN.
- No reutilizar el último topic de los metadatos de alerta como topic observado del
  frame para ingeniería de features.

## 3.6 Faltantes: contrato único por consumidor

1. XGBoost e híbrido conservan NaN en features no observables. Rechazar infinitos
   en la matriz final; no hacer pasar errores numéricos como observaciones válidas.
2. Para LSTM/autoencoder, ajustar medias e imputación **solo en train**; columna
   completamente ausente en train usa relleno 0. Ajustar scaler sobre train imputado.
3. Transformar con esas estadísticas y fijar 0 en posiciones originalmente ausentes
   después de escalar. Añadir máscaras `missing__<feature>` para las columnas del
   contrato que permiten NaN; orden fijo, valores 0/1, máscaras sin escalar.
4. Mantener `fe_has_mqtt`, pero no usarlo como única máscara para identidad, CONNECT,
   topics y contexto L2. Son ausencias diferentes.
5. Separar esquema tabular y esquema de tensor. El híbrido usa features tabulares
   originales más MSE; no reutiliza las columnas imputadas del tensor como si fueran
   la matriz de XGBoost.
6. Escribir helpers compartidos por adapters y funciones espejo del notebook. Exportar
   mediante código estadísticas necesarias, columnas, máscaras y política versionada.
7. Antes de inferencia comprobar finitud de tensor y MSE. Un NaN no puede terminar
   silenciosamente como `normal` por una comparación falsa contra el umbral.

## Pruebas a escribir, todas para ejecución final

- Límites exactos de 1 s/5 s/100 µs, timestamps iguales y retrocesos.
- Separación entre capturas, particiones, orígenes, conexiones y direcciones.
- Reinicio por truncado/rotación y reutilización de `tcp.stream`.
- Replay de registros crudos por fuente → contexto → features → tensor; compararlo
  con el notebook sin inyectar columnas `_ctx_*` ya calculadas offline.
- Igualdad numérica de features, imputación, tensor y MSE; no solo igualdad de labels.
- Casos TCP, L2, MQTT ausente, identidad ausente y columnas completamente vacías.

## Cierre de código

- [ ] Fórmulas, relojes, claves y reinicios son explícitos y equivalentes.
- [ ] Preprocesado LSTM e híbrido ya no omite imputación/máscaras.
- [ ] Contratos actualizados en generadores, adapters y documentación.
- [ ] Regresión histórica registrada como pendiente de evaluación final.
- [ ] Ningún entrenamiento, test ni actualización de artefactos ejecutado.
