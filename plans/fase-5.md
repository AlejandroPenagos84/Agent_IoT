# Fase 5 — Preparar evaluación y ejecución final del usuario

Leer primero [README.md](README.md). **El agente escribe esta fase; no la ejecuta.**
La fase termina al entregar código, pruebas y un único procedimiento final al usuario.

## 5.1 Evaluación agrupada de cinco folds

1. Mantener `StratifiedGroupKFold`, cinco folds y semilla 42, con conexiones/episodios
   completos como grupos. Guardar asignaciones mediante IDs de fila estables.
2. Para iteración `k=0..4`: test=fold k, validation=fold `(k+1)%5`, train=los tres
   restantes. No buscar otra combinación para ocultar falta de cobertura.
3. Reconstruir conjuntos conocidos, contextos, imputación y scaler dentro de cada
   partición/ajuste. No reutilizar una matriz con estado aprendido globalmente.
4. Si falta una clase en train de un modelo supervisado, marcar ese modelo/fold no
   entrenable con causa. No remapear clases ni introducir muestras sintéticas.
5. Si faltan clases en test o ventanas evaluables, reportar cobertura y métricas
   afectadas como `None`. No descartar folds del informe ni sustituir indefinidos por 0.
6. Guardar versiones, semillas, configuración, población y fingerprint de datos/código.
   Estos registros se producirán en la ejecución final, no durante la implementación.

## 5.2 Híbrido sin MSE in-sample

Usar MSE **out-of-fold dentro del train externo**, sin convertir validation externo
en entrenamiento del segundo nivel:

1. Dividir train externo en tres folds internos agrupados, semilla 42.
2. Para cada fold interno, ajustar allowlists, preprocesado y autoencoder únicamente
   con los otros dos; generar features y MSE para el fold retenido con estado separado.
3. Concatenar filas finales retenidas en su orden original para entrenar el XGBoost
   multiclase del híbrido. Target = clase de la última fila. Pesos sobre esas filas.
4. Para validation/test externos e inferencia, ajustar el componente base con todo
   train externo. Conservar la definición y el orden de features de los folds internos.
5. No suplir MSE OOF ausente con MSE in-sample. Registrar filas/folds no evaluables y
   verificar cobertura de las cuatro clases antes de ajustar el segundo nivel.
6. Documentar que el auxiliar final usa más datos que los auxiliares OOF. La paridad
   notebook/adapter se verifica con ese mismo auxiliar final exportado.

## 5.3 Métricas y cobertura

Preparar resultados para XGBoost sobre todos los frames, XGBoost con ventanas del
agente, LSTM supervisado e híbrido. Comparación común sobre las mismas filas finales.
Autoencoder binario en sección independiente, con nombre y target explícitos.

- Matriz 4×4 en orden fijo; precision, recall y F1 por clase, accuracy, balanced
  accuracy, macro-F1 y AUC macro OvR cuando estén definidas. Informar soporte.
- Recall de detección por tipo: ataque predicho como cualquiera de las tres clases
  de ataque. Recall de identificación por tipo: clase predicha exactamente correcta.
- FP normal: normales predichos como cualquier ataque / normales evaluables.
- Recall e2e de identificación: ataques de clase c correctamente identificados /
  todos los ataques de clase c asignados a test, incluidos los sin ventana.
- Frames rechazados antes del agrupamiento: reportar conteos y causas aparte. Si no
  tienen asignación de test válida, no inventarla ni llamar «e2e de todo el dataset»
  al cociente sobre la población seleccionada. Declarar expresamente el denominador.
- Reportar recibidos, aceptados, con ventana y predichos, por TCP/L2 y clase.
  Una predicción que el agente no emitiría antes del frame 11 no cuenta como online.
- Media y desviación poblacional (`ddof=0`) entre folds válidos, junto a número de
  folds válidos. `allow_nan=False`; no serializar NaN/Infinity en métricas.
- Número de grupos independientes por clase. Umbral diagnóstico inicial: 5 grupos
  con esa clase por partición; por debajo, marcar evidencia limitada sin ocultar el
  resultado. No presentarlo como garantía estadística ni buscar otro split para cumplirlo.

## 5.4 Evaluación temporal adicional

Preparar split cronológico por captura/segmento: cortes en percentiles temporales
60 y 80, dejando grupos completos dentro de train/validation/test. Excluir y contar
grupos que atraviesen un corte, sin partirlos ni trasladar futuro a train.
Construir features después de esa selección con el mismo aislamiento de estado.

Si hay episodios reales documentados, reportar también su cobertura. Sin esa metadata,
no inventar episodios de ataque desde labels ni llamar al split temporal prueba de
generalización entre ataques independientes. Registrar cobertura insuficiente como tal.

## 5.5 Ablations y selección sin ejecuciones por fase

Preparar para la única campaña final estas comparaciones diagnósticas, sin búsqueda
automática de hiperparámetros ni selección automática de otra implementación:

- Origen: configuración final frente a la misma configuración sin
  `fe_origen_conocido` ni `fe_origen_observable`, sobre train/validation. Reajustar los
  modelos afectados con su esquema correspondiente; no rellenar las columnas con 0.
- Autoencoder A: misma matriz tabular final, imputación de train y cero post-escalado,
  sin máscaras, con decoder recurrente que produce directamente las features.
- Autoencoder B: igual que A, añadiendo únicamente las máscaras de fase 3.
- Autoencoder C: igual que B, añadiendo únicamente la proyección del decoder de fase 4.
  A/B/C usan mismas filas, ventanas, semillas, épocas y target binario de evaluación.
  Cada variante ajusta sus propios artefactos; B−A y C−B separan ambos efectos.
- Pruebas de paridad y cobertura L2 descritas en fase 3.

El candidato programado es la configuración completa con origen y autoencoder C.
Los diagnósticos no lo convierten automáticamente en modelo aceptado: el usuario
revisará los resultados antes de publicarlo. No reconstruyen exactamente la fase 3.6
histórica porque la matriz tabular final incorpora otros cambios; declararlo.

No reconstruir seis pipelines históricos completos para poder avanzar. Los reportes
viejos siguen siendo referencias históricas. Configuraciones candidatas y cualquier
regla de selección futura deben quedar fijadas antes de mirar test; no elegir el fold
con mejor test.
No exigir aumentos de métricas para considerar terminada la escritura de código.

## 5.6 Un procedimiento final, ejecutado por el usuario

Crear `tests/run_final_validation.py` como orquestador, con argumentos obligatorios
`--data-dir` y `--output-dir`. La salida debe ser un directorio nuevo, ajeno a
`modelos_agente/`; rechazar destinos existentes para evitar sobreescrituras.
No instalar paquetes, iniciar contenedores ni copiar artefactos al directorio principal.

El orquestador deberá, cuando **el usuario lo ejecute**:

1. Comprobar dependencias/datos y validar estáticamente el notebook.
2. Ejecutar compilación y unittest; detenerse y describir fallos.
3. Crear copia del notebook con rutas locales y ejecutar de principio a fin, con
   evaluación agrupada/temporal y ablations previstas. No mutar el notebook original.
4. Cargar el paquete candidato y comprobar paridad real de features, tensores,
   probabilidades, MSE y labels con los adapters, usando casos TCP y L2.
5. Producir informe de cobertura, métricas, errores y manifiesto del paquete.

Entregar este ejemplo como comando **para el usuario**, nunca ejecutarlo el agente:

```bash
python tests/run_final_validation.py --data-dir /RUTA/A/CSV --output-dir /RUTA/NUEVA/validacion-final
```

`--data-dir` debe contener `DoS.csv`, `MitM.csv` e `Intrusion.csv`. No asumir que
`data/` o `dataset/` existe, ni crear datasets faltantes. El notebook original
conservará además su ejecución directa en Kaggle.

## 5.7 Paquete final

Programar la exportación de una configuración candidata coherente. Usar el split
externo k=0 para el paquete de referencia, no el mejor fold por test. Si no es
entrenable, registrar que no hay candidato; no sustituirlo en silencio.

El paquete incluye modelos XGBoost, LSTM supervisado y auxiliar; encoder multiclase;
scaler/estadísticas/máscaras; known origins/topics; config versionado; métricas y
manifiestos de features, datos y split. Describir separadamente columnas tabulares,
columnas escaladas y columnas del tensor. No hacer fallback silencioso a artefactos viejos.

No reentrenar con test para producir el paquete evaluado. Un entrenamiento posterior
con más datos sería otro artefacto, no el modelo al que pertenecen esas métricas.
La copia conjunta a `modelos_agente/` la realizará el usuario después de revisar todo.

## Cierre de código y entrega

- [ ] Orquestador, evaluación y exportación escritos, sin ejecución.
- [ ] Pruebas cubren cuatro clases, causalidad, L2, faltantes y paridad completa.
- [ ] README de carpetas afectadas y notebook describen la implementación preparada.
- [ ] No se modificaron artefactos principales ni resultados históricos.
- [ ] Entrega enumera limitaciones y declara: «No se ejecutaron pruebas ni entrenamientos».
- [ ] Validación, aceptación de rendimiento y actualización final quedan a cargo del usuario.
