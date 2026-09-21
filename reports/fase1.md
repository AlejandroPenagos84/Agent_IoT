# Fase 1 — pesos balanceados por cuatro clases

Fecha de ejecución: 2026-09-21.

Esta fase modifica el cálculo de `sample_weight` de `fit_classifier`. El modelo
sigue siendo **binario** (`normal`/`ataque`); lo que cambia es que los pesos se
calculan con las **cuatro clases** (`normal`, `DoS`, `mitm`, `intrusion`) en vez de
con la etiqueta binaria. No se tocaron features, particiones, scaler, umbral ni
`pipeline_config.json`.

## Cambio implementado

`ml-mqtt-model.ipynb`:

```python
def fit_classifier(features, labels, labels_4clases):
    model = get_xgb_model()
    model.fit(features, labels,
              sample_weight=compute_sample_weight('balanced', np.asarray(labels_4clases)))
    return model
```

Los dos puntos de llamada:

1. XGBoost sobre frames:
   `fit_classifier(X.iloc[train_idx], y_bin.iloc[train_idx], y.iloc[train_idx])`.
2. Híbrido, con las etiquetas de la **última fila** de cada ventana de train:
   `labels_4clases_train = y.iloc[window_rows['train'][:, -1]].to_numpy()`.

Distribución de las etiquetas 4-clase usadas para los pesos (solo train):

| Conjunto | normal | DoS | mitm | intrusion |
| --- | ---: | ---: | ---: | ---: |
| XGBoost (frames) | 140.952 | 27.309 | 2.126 | 1.139 |
| Híbrido (última fila de ventana) | 101.375 | 22.427 | 1.813 | 50 |

El LSTM no usa `fit_classifier`, por lo que no cambia. El umbral del LSTM siguió
calibrándose solo con ventanas normales de validación.

## Partición

Idéntica a la línea base opción A: `SEED = 42`, `test_fold = 0`, `val_fold = 1`,
`train_folds = 2, 3, 4`; `L2_EPISODE_GAP_SECONDS = 1.0`. La población no cambia,
así que la comparación es válida.

## Antes → después

Línea base “Antes”: `reports/fase0-opcion-a.md` (misma partición). “Después”:
`tmp/fase1/diagnostics.json`.

### XGBoost (todos los frames)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9834 | 0,9729 | −0,0105 |
| Macro-F1 | 0,9766 | 0,9390 | −0,0376 |
| AUC | 0,9981 | 0,9977 | −0,0004 |
| Recall DoS | 0,9925 | 0,9932 | +0,0007 |
| Recall MitM | 0,8138 | 0,9605 | **+0,1467** |
| Recall intrusion | 0,9684 | 0,9789 | +0,0105 |
| FP normal | 1,2408 % | 4,4653 % | **+3,2245 pp** |

### XGBoost (frames con ventana)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9904 | 0,9797 | −0,0107 |
| Macro-F1 | 0,9898 | 0,9559 | −0,0339 |
| AUC | 0,9991 | 0,9991 | 0,0000 |
| FP normal | 0,4288 % | 3,4156 % | **+2,9868 pp** |

### LSTM (sin cambios)

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9252 | 0,9252 | 0,0000 |
| Macro-F1 | 0,9213 | 0,9213 | 0,0000 |
| AUC | 0,9259 | 0,9259 | 0,0000 |
| Recall DoS (cond.) | 0,9664 | 0,9664 | 0,0000 |
| Recall MitM (cond.) | 0,0329 | 0,0329 | 0,0000 |
| Recall intrusion (cond.) | 0,7222 | 0,7222 | 0,0000 |
| FP normal | 3,4506 % | 3,4506 % | 0,0000 |

La coincidencia exacta confirma que la modificación solo afecta a los dos
clasificadores que usan `fit_classifier`.

### Híbrido LSTM + XGBoost

| Métrica | Antes | Después | Δ |
| --- | ---: | ---: | ---: |
| Balanced accuracy | 0,9915 | 0,9876 | −0,0039 |
| Macro-F1 | 0,9917 | 0,9762 | −0,0155 |
| AUC | 0,9989 | 0,9986 | −0,0003 |
| Recall DoS | 0,9950 | 0,9953 | +0,0003 |
| Recall MitM | 0,8891 | 0,9601 | **+0,0710** |
| Recall intrusion | 0,3889 | 0,7222 | **+0,3333** |
| FP normal | 0,3046 % | 1,6886 % | **+1,3840 pp** |

## Recall por tipo (condicionado y extremo a extremo)

“Evaluables” y recall condicionado usan solo frames/ventanas que terminan una
ventana completa. El recall e2e de test usa todos los frames de ataque de test
como denominador.

| Modelo | Tipo | Frames test | Evaluables | Detectados | Recall cond. | Recall e2e test |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | DoS | 9.103 | 9.103 | 9.041 | 0,9932 | 0,9932 |
| XGBoost | MitM | 709 | 709 | 681 | 0,9605 | 0,9605 |
| XGBoost | intrusion | 380 | 380 | 372 | 0,9789 | 0,9789 |
| LSTM | DoS | 9.103 | 7.466 | 7.215 | 0,9664 | 0,7926 |
| LSTM | MitM | 709 | 577 | 19 | 0,0329 | 0,0268 |
| LSTM | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |
| Híbrido | DoS | 9.103 | 7.466 | 7.431 | 0,9953 | 0,8163 |
| Híbrido | MitM | 709 | 577 | 554 | 0,9601 | 0,7814 |
| Híbrido | intrusion | 380 | 18 | 13 | 0,7222 | 0,0342 |

Semánticas: XGBoost `frame`; LSTM `any-in-window; tipo=last-frame`; híbrido
`last-frame`. El LSTM conserva la etiqueta binaria `any-in-window`.

## Criterios de aceptación

| Criterio | XGBoost | Híbrido | ¿Cumple? |
| --- | --- | --- | --- |
| Recall MitM no disminuye | 0,8138 → 0,9605 | 0,8891 → 0,9601 | **Sí** |
| Recall intrusion no disminuye | 0,9684 → 0,9789 | 0,3889 → 0,7222 | **Sí** |
| FP normal no aumenta > 1 pp | +3,2245 pp | +1,3840 pp | **No** |

La fase **no cumple** los criterios de aceptación: aunque sube el recall de las
clases minoritarias (MitM e intrusion), el falso positivo de `normal` aumenta
mucho más de 1 punto porcentual y caen balanced accuracy y macro-F1 en todos los
modelos afectados. No se afirma una mejora global.

## Interpretación

- Los pesos 4-clase reducen el peso total de `normal` de `N/2` a `N/4` y suben el
  peso de MitM e intrusion. El efecto medido es exactamente ese: más sensibilidad
  a ataques raros, a costa de más falsos positivos en `normal`.
- El salto de recall MitM en XGBoost (0,8138 → 0,9605) y de intrusion en el
  híbrido (0,3889 → 0,7222) es grande, pero no compensa el aumento de FP normal
  bajo el criterio fijado.
- El AUC apenas cambia; el deterioro de balanced accuracy y macro-F1 proviene del
  desbalance de las predicciones, no de la capacidad de ranking.

## Qué se ejecutó

- Notebook completo sobre los tres CSV reales, 100 árboles y 10 épocas, en CPU.
- XGBoost de frames, LSTM autoencoder, híbrido y XGBoost restringido a frames
  con ventana.
- `tmp/fase1/prepare_phase1_run.py` con rutas locales y celda de diagnóstico.
- Entorno: Python 3.11.16, NumPy 2.4.6, pandas 3.0.5, scikit-learn 1.9.1,
  XGBoost 3.2.0, PyTorch 2.14.0+cu130 sobre CPU.

Archivos reproducibles:

- `tmp/fase1/ml-mqtt-model-fase1.ipynb`;
- `tmp/fase1/ml-mqtt-model-fase1-executed.ipynb`;
- `tmp/fase1/diagnostics.json`;
- `tmp/fase1/modelos_agente/` (artefactos temporales de esta ejecución).

## Qué no se ejecutó

- No se usaron datos sintéticos.
- No se modificaron `modelos_agente/` de la raíz; los artefactos quedan solo en
  `tmp/fase1/`.
- No se hizo rotación de cinco folds ni split temporal/episódico; corresponden a
  la Fase 5.
- No se ejecutó la suite `tests/` en esta misma corrida.

## Qué continúa sin verificar

- Si el aumento de FP normal puede mitigarse con un compromiso intermedio (por
  ejemplo, mezclar pesos binarios y por tipo, o ajustar el umbral de decisión).
- La generalización de MitM en validation, que sigue concentrada en 2 grupos con
  esa clase.
- El mecanismo exacto de etiquetado de MitM e intrusion del dataset.
- El desempeño de despliegue sobre MQTTS y capturas independientes.

## Decisión requerida

La Fase 1 queda implementada y medida, pero **no cumple el criterio de FP normal**.
Antes de continuar con la Fase 2 hay que elegir:

- **Conservar** el cambio pese al aumento de FP y registrarlo como compromiso
  explícito; o
- **Revertir** el cambio en `ml-mqtt-model.ipynb` y no exportar estos artefactos,
  de modo que la línea base opción A siga siendo la referencia.
