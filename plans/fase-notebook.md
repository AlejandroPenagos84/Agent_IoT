# Fase notebook — Legibilidad sin cambios de comportamiento

## Objetivo y autorización

Leer primero [README.md](README.md). Esta fase es exclusivamente editorial:
hacer `ml-mqtt-model.ipynb` más fácil de recorrer, comprender y mantener.
**Conservar todo el código existente y su orden. Si un bloque ya es claro, dejarlo.**

Este documento es un plan, no una autorización para ejecutar el notebook.
El agente que implemente esta fase solo editará su estructura y explicaciones;
el usuario ejecutará la validación al terminar todo el trabajo.

En la secuencia general, aplicar esta fase después de escribir las fases 0–5 y
antes de la ejecución final del usuario. Si se encarga por separado, trabajar sobre
el notebook que exista en ese momento, sin implementar tareas de las demás fases.

## Diagnóstico de la versión inspeccionada

La versión leída el 2026-09-21 tiene 23 celdas, ya describe cuatro clases y contiene
rotación de folds, evaluación temporal, ablations y exportación. No reemplazarla por
una versión binaria anterior ni asumir el estado histórico de los otros planes.

Las principales dificultades de lectura son:

- Celda 7: aproximadamente 256 líneas de parsers, construcción de features y
  distintos estados causales, con pocas separaciones explicativas.
- Celda 18: aproximadamente 218 líneas que mezclan definiciones, ejecución del
  entrenamiento, liberación de estado y agregación de métricas.
- Celda 22: aproximadamente 248 líneas de selección del candidato, muestras de
  paridad, serialización de modelos, config, métricas y ZIP.
- Celdas 3, 5 y 14: bloques de más de 130 líneas con varias responsabilidades.
- La sección markdown de features reúne tablas extensas y explicaciones de distintas
  etapas; contiene referencias antiguas como «17 features» que deben contrastarse
  con las listas actuales antes de conservar esa descripción.

Los índices anteriores son referencias de esta inspección, empezando en cero.
Identificar bloques por su contenido; no programar ediciones dependientes de esos
índices, porque cambiarán al dividir celdas.

## Límites estrictos

### Permitido

- Añadir o mejorar celdas markdown, índice, títulos, subtítulos y explicaciones.
- Dividir una celda de código entre instrucciones completas de nivel superior.
- Insertar comentarios breves y líneas en blanco para explicar bloques largos.
- Redistribuir texto markdown existente entre subsecciones sin perder información.
- Corregir ortografía de la prosa y descripciones claramente desactualizadas,
  siempre basándose en el código actual y sin modificarlo para justificar el texto.

### Fuera de alcance

- Eliminar código, incluso si parece redundante, sin uso o incorrecto.
- Renombrar funciones, variables, clases, claves, archivos o artefactos.
- Extraer funciones nuevas, mover lógica a módulos o introducir imports.
- Modificar fórmulas, features, targets, splits, pesos, modelos, defaults o métricas.
- Cambiar rutas, hiperparámetros, semillas, flags, selección de fold o exportaciones.
- Reordenar instrucciones, definiciones, asignaciones, entrenamiento, llamadas a
  `.cpu()`/`.eval()`, limpieza de estado o escrituras. También conservar asignaciones
  repetidas como `FINAL_FOLD = 0`; no deduplicarlas como parte de esta fase.
- Añadir llamadas a `display`, nuevos `print`, gráficos, cálculos o muestras para
  «hacerlo visual». Esta fase mejora presentación sin añadir cómputo.
- Cambiar docstrings si se exige conservar el AST: las explicaciones nuevas van
  preferiblemente en markdown o comentarios `#`.
- Ejecutar celdas, entrenamiento, tests, validadores, `py_compile` o inferencia.
- Borrar outputs históricos o modificar `modelos_agente/`.

Si aparece un posible bug, anotarlo en la entrega con su ubicación. No corregirlo
en esta fase ni presentar la mejora de legibilidad como validación de su lógica.

## Estructura de lectura

Conservar el flujo actual. Añadir un índice markdown con enlaces internos a los
títulos principales. Usar anchors explícitos cuando sea necesario para evitar
dependencia de cómo Kaggle/Jupyter convierten acentos en enlaces.

| Sección | Subdivisiones, en el orden del código actual |
| --- | --- |
| Presentación | Objetivo, modelos existentes, entradas/salidas y límites MQTT/L2 |
| Preparación | Imports; parámetros y selección de dispositivo |
| 1. Carga y contexto | Rutas/contratos; definición de carga; lectura y resumen |
| 2. Features y diagnóstico | Criterios/tablas; helpers y catálogos; diagnóstico; builders por responsabilidad; matriz inicial |
| 3. Particiones y ventanas | IDs de grupo/dirección; ventanas; folds; split temporal; creación de folds |
| 4. Estado por partición | Normalización de claves; estado aprendido, contextos y preprocesado |
| 5. Modelos y entrenamiento | XGBoost; clases LSTM/autoencoders; pesos; entrenamiento; construcción de secuencias; predicción/MSE |
| 6. Métricas | Multiclase; detección/identificación; referencia binaria; agregación y serialización |
| 7. Evaluación agrupada | Folds internos; generación OOF; evaluación de partición; helpers; ejecución; agregación/resumen |
| 8. Evaluación adicional | Split temporal; ablation de origen; variantes del autoencoder |
| 9. Exportación | Candidato; preparación de referencias; paridad; modelos y preprocesado; configuración; métricas/manifiestos; ZIP |

Esta tabla define una organización editorial, no autoriza cambiar el orden para
agrupar por afinidad. Cuando las instrucciones estén intercaladas, conservarlas
y añadir subtítulos en sus posiciones actuales. No mover flags al principio del
notebook si actualmente se asignan más adelante.

## Desglose concreto de los bloques extensos

### Features: actual celda 7

Separar, sin cambiar orden ni cuerpos de funciones:

1. Constantes y decodificación de `hdrflags`.
2. `topic_wildcard`.
3. `build_network_features`.
4. `add_connect_context`.
5. `build_direction_bytes_rate`.
6. `build_origin_context`.
7. `_multicast_flag` y `build_l2_context`.
8. `build_mqtt_features` y `build_feature_matrix`.

Antes de cada bloque explicar qué transforma, qué estado utiliza y qué devuelve.
Distinguir par MAC para episodios, MAC origen para contexto L2 y dirección para tasa
de bytes. Describir lo que el cuerpo efectivamente hace; no atribuir garantías que
solo estén en el plan y todavía no aparezcan implementadas.

### Evaluación: actual celda 18

Separar por límites completos de nivel superior:

1. `inner_folds_for`.
2. `oof_hybrid_training_rows`.
3. `evaluate_partition` completo.
4. Helpers `fold_metric` y `nested_metric`.
5. Flags, selección de fold y ejecución de la rotación, manteniendo el orden.
6. Liberación del estado que no corresponde al candidato.
7. Constantes de resumen y `aggregate_rotation`.
8. Cálculo e impresión del resumen.

No partir `evaluate_partition` en funciones nuevas. Si sigue siendo largo, añadir
comentarios que delimiten sus bloques actuales: estado, ventanas, XGBoost, LSTM,
autoencoder, híbrido y reporte. Conservar excepciones y control de flujo.

### Exportación: actual celda 22

Separar en celdas consecutivas sin adelantar definiciones ni escrituras:

1. Selección/guardas del fold y referencias a modelos/estado.
2. Preparación de matrices finales y directorio de salida.
3. `sequence_tensor` y `build_parity_payload`.
4. Escritura de muestras de paridad.
5. Serialización de modelos, scaler y encoder.
6. Escritura de conjuntos conocidos y estadísticas de faltantes.
7. Construcción del diccionario `config` completo y su escritura.
8. Manifiesto de particiones y su escritura.
9. Métricas y su escritura.
10. Empaquetado ZIP y mensaje final.

No separar un diccionario, bloque `with`, bucle, clase, función o expresión a medias.
Si `config` o una función ocupa más de 100 líneas, conservarla íntegra y explicar
sus grupos de campos en markdown; una cifra de líneas no justifica cambiar lógica.

## Reglas de prosa y presentación

- Un título debe decir qué hace el bloque, por ejemplo «Contexto causal por MAC
  origen», en vez de usar únicamente «Fase 3.4» o «Helpers».
- Mantener referencias a fases como información secundaria, sin exigir leer los
  planes para entender el notebook.
- Antes de bloques relevantes, añadir 2–4 frases: propósito, entradas, salidas y
  cuándo se ejecuta. No repetir cada línea de Python en español.
- Diferenciar «Define funciones; no entrena» de «Al ejecutar esta celda se entrenan
  modelos» y «Al ejecutar esta celda se escriben artefactos».
- Mantener visibles fórmulas, unidades, claves de agrupación y límites de observación.
- Aclarar la diferencia entre matriz tabular, tensor escalado con máscaras y MSE.
- Conservar tablas útiles; dividirlas por tema si son extensas. No reemplazar una
  tabla completa por «ver código» ni borrar diagnósticos para acortar el documento.
- Evitar afirmar mejoras, corrección de bugs o nuevas métricas por reorganizar celdas.
- El índice no invita a ejecutar secciones aisladas: aclarar que el flujo requiere
  ejecución de arriba abajo en kernel limpio, a cargo del usuario.

## Preservación y compatibilidad

1. Usar una edición estructural del notebook; no reconstruir todo el JSON manualmente.
   Conservar metadata de kernel, formato, attachments y celdas ajenas al trabajo.
2. Conservar IDs de celdas no modificadas; al dividir, retener el ID original en el
   primer fragmento y asignar IDs únicos a los nuevos. No regenerar todos los IDs.
3. No borrar outputs ni limpiar todo el notebook. Si la celda dividida tiene outputs,
   conservar su lista completa y orden, una sola vez en el último fragmento del grupo;
   añadir una nota markdown de que corresponden a la celda original antes de dividir.
   No duplicar gráficos, mensajes, execution counts ni fabricar una ejecución nueva.
   Nuevos fragmentos tendrán `execution_count=null`; el fragmento que conserva los
   outputs puede conservar su contador histórico con esa advertencia explícita.
4. Si no hay outputs, mantenerlos vacíos. No rellenarlos con reportes históricos.
5. Conservar literales usados por `tests/validate_notebook.py` y las sustituciones de
   rutas/flags de `tests/run_final_validation.py`. Se revisaron por lectura y operan
   sobre fuentes de celdas; no necesitan una cantidad fija de celdas de código.
6. No editar validators/tests para hacer pasar una reorganización. Si se descubre
   otra dependencia real de índices o fuente exacta, documentarla antes de ampliar
   alcance; buscar primero una división que conserve esa compatibilidad.

## Comprobación de que solo cambió la presentación

Durante la implementación: inspección textual del diff y mapa de bloques originales
→ celdas nuevas. Confirmar que cada instrucción sigue apareciendo una vez y en el
mismo orden, incluidas asignaciones repetidas que ya existían.

Para la validación final del usuario, recomendar comparar el AST concatenado de
las celdas de código antes/después, ignorando posiciones de línea. Debe ser igual;
comentarios, espacios y límites entre celdas no deben cambiarlo. La igualdad del AST
no prueba ejecución independiente ni orden del estado del kernel; por eso también
se conserva el orden y se requiere la validación final ya prevista.

No ejecutar esa comparación, tests ni notebook durante esta fase. En la entrega,
distinguir inspección textual realizada de comprobaciones pendientes de ejecución.

## Entregable y criterio de cierre

- [ ] Notebook con índice y subtítulos descriptivos.
- [ ] Celdas extensas divididas donde existen límites naturales completos.
- [ ] Ninguna instrucción eliminada, renombrada, reordenada o cambiada.
- [ ] Funciones grandes conservadas si dividirlas exigiría un refactor.
- [ ] Markdown describe el código vigente, no una implementación futura supuesta.
- [ ] Rutas, flags, outputs existentes y metadata preservados según estas reglas.
- [ ] Posibles defectos funcionales solo anotados para otra tarea.
- [ ] Entrega indica: «Solo se mejoró la organización y explicación; no se ejecutó
  el notebook ni se validaron sus resultados».

Si un bloque ya cumple estas condiciones, no modificarlo.
