"""
Motor de inferencia: carga los modelos exportados por el notebook y los aplica a
trafico MQTT/IoT.

Es una libreria: los adaptadores de `classifiers/` importan `MQTTDetector` y exponen
una interfaz uniforme `predict(window)`.

Metodos de prediccion:
    predecir_caso1(df)      XGBoost full        -> nombres de clase
    predecir_tls(df)        XGBoost cifrado     -> nombres de clase
    predecir_anomalia(df)   LSTM AE             -> 0 normal / 1 ataque
    predecir_hibrido(df)    XGBoost + LSTM      -> nombres de clase (modelo por defecto)

CLI:
    python agent_inference.py <model_dir> <archivo.csv>
    Imprime la prediccion hibrida, una etiqueta por linea.

IMPORTANTE (categoricas de XGBoost): una categoria nueva puede producir error al
predecir; en produccion se debe mapear a 'NOT_MQTT' antes de llamar a predict.
"""

import argparse
import json
import math
import os
from collections import Counter

import numpy as np
import pandas as pd
import joblib

import torch
from xgboost import XGBClassifier

SEQ_LEN = 10
NAN_FILL = -1.0
COLS_RED = [
    'frame.time_delta', 'frame.time_delta_displayed', 'frame.time_relative',
    'frame.len', 'frame.cap_len', 'tcp.srcport', 'tcp.dstport',
]


def _entropia(texto):
    if pd.isna(texto) or not str(texto):
        return 0.0
    cadena = str(texto)
    probs = [c / len(cadena) for c in Counter(cadena).values()]
    return -sum(p * math.log2(p) for p in probs)


def _crear_secuencias(data, seq_length=SEQ_LEN):
    """Ventanas deslizantes. Devuelve (secuencias, índices de la fila final)."""
    xs, end_idx = [], []
    for i in range(len(data) - seq_length):
        xs.append(data[i:i + seq_length])
        end_idx.append(i + seq_length - 1)
    return np.array(xs), np.array(end_idx)


class MQTTDetector:
    def __init__(self, model_dir, device=None):
        self.model_dir = model_dir

        with open(os.path.join(model_dir, 'pipeline_config.json')) as f:
            self.cfg = json.load(f)

        self.le = joblib.load(os.path.join(model_dir, 'le_target.joblib'))
        self.scaler = joblib.load(os.path.join(model_dir, 'scaler.joblib'))
        self.threshold = self.cfg['threshold']

        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')

        # ── XGBoost ──
        self.xgb_case1 = XGBClassifier(enable_categorical=True)
        self.xgb_case1.load_model(os.path.join(model_dir, 'xgb_case1.ubj'))

        self.xgb_tls = XGBClassifier(enable_categorical=True)
        self.xgb_tls.load_model(os.path.join(model_dir, 'xgb_tls.ubj'))

        self.xgb_hybrid = XGBClassifier(enable_categorical=True)
        self.xgb_hybrid.load_model(os.path.join(model_dir, 'xgb_hybrid.ubj'))

        # ── LSTM Autoencoder (TorchScript) ──
        self.lstm = torch.jit.load(os.path.join(model_dir, 'lstm_ae.pt'),
                                   map_location=self.device)
        self.lstm.eval()

    # ───────────── preprocesado (replica el notebook) ─────────────
    @staticmethod
    def feature_engineering(df):
        df = df.copy()
        cols_ruido = [
            'ip.src', 'ip.dst', 'frame.comment', 'frame.comment.expert',
            'frame.coloring_rule.name', 'frame.coloring_rule.string',
            'frame.interface_name', 'frame.interface_id', 'frame.file_off',
        ]
        df.drop(columns=[c for c in cols_ruido if c in df.columns],
                errors='ignore', inplace=True)

        if 'mqtt.msg' in df.columns:
            df['fe_msg_entropy'] = df['mqtt.msg'].astype(str).apply(_entropia)
        if 'mqtt.topic' in df.columns:
            df['fe_topic_entropy'] = df['mqtt.topic'].astype(str).apply(_entropia)
            df['fe_topic_depth'] = df['mqtt.topic'].astype(str).apply(
                lambda x: 0 if x == 'nan' else x.count('/') + 1)
        if 'mqtt.len' in df.columns and 'frame.len' in df.columns:
            df['mqtt.len'] = pd.to_numeric(df['mqtt.len'], errors='coerce').fillna(0)
            df['frame.len'] = pd.to_numeric(df['frame.len'], errors='coerce').fillna(0)
            df['fe_payload_ratio'] = df['mqtt.len'] / (df['frame.len'] + 1e-5)
        if 'mqtt.msgtype' in df.columns and 'mqtt.conflag.uname' in df.columns:
            df['mqtt.msgtype'] = pd.to_numeric(df['mqtt.msgtype'], errors='coerce').fillna(-1)
            df['mqtt.conflag.uname'] = pd.to_numeric(df['mqtt.conflag.uname'], errors='coerce').fillna(-1)
            df['fe_anon_connect'] = ((df['mqtt.msgtype'] == 1)
                                     & (df['mqtt.conflag.uname'] == 0)).astype(int)
        return df

    def _build_case1(self, df):
        df = self.feature_engineering(df)
        cols = self.cfg['feature_columns_case1']
        X = df.reindex(columns=cols).copy()
        for c in X.columns:
            if (pd.api.types.is_object_dtype(X[c])
                    or pd.api.types.is_bool_dtype(X[c])):
                X[c] = (X[c].astype(str)
                          .replace({'nan': 'NOT_MQTT', 'None': 'NOT_MQTT'})
                          .fillna('NOT_MQTT')
                          .astype('category'))
            else:
                X[c] = pd.to_numeric(X[c], errors='coerce').fillna(NAN_FILL)
        return X[cols]

    def _build_tls(self, df):
        base = df[[c for c in COLS_RED if c in df.columns]].copy()
        for c in COLS_RED:
            if c not in base.columns:
                base[c] = np.nan
        base = base[COLS_RED]
        for c in base.columns:
            base[c] = pd.to_numeric(base[c], errors='coerce').fillna(NAN_FILL)

        base['fe_bytes_per_sec'] = base['frame.len'] / (base['frame.time_delta'] + 1e-6)
        base['fe_cap_ratio'] = base['frame.cap_len'] / (base['frame.len'] + 1e-6)
        base['fe_is_standard_mqtt_port'] = base['tcp.dstport'].isin([1883, 8883]).astype(int)
        return base[self.cfg['feature_columns_tls']]

    def _build_lstm_raw(self, df):
        base = df[[c for c in COLS_RED if c in df.columns]].copy()
        for c in COLS_RED:
            if c not in base.columns:
                base[c] = np.nan
        base = base[COLS_RED]
        for c in base.columns:
            base[c] = pd.to_numeric(base[c], errors='coerce').fillna(NAN_FILL)
        return base

    def _recon_mse(self, xs, batch_size=1024):
        mse_all = []
        with torch.no_grad():
            for i in range(0, len(xs), batch_size):
                batch = torch.tensor(xs[i:i + batch_size], dtype=torch.float32).to(self.device)
                out = self.lstm(batch)
                mse_all.append(torch.mean((out - batch) ** 2, dim=[1, 2]).cpu().numpy())
        return np.concatenate(mse_all) if mse_all else np.array([])

    # ───────────── métodos de predicción ─────────────
    def predecir_caso1(self, df):
        X = self._build_case1(df)
        pred = self.xgb_case1.predict(X)
        return self.le.inverse_transform(pred)

    def predecir_tls(self, df):
        X = self._build_tls(df)
        pred = self.xgb_tls.predict(X)
        return self.le.inverse_transform(pred)

    def predecir_anomalia(self, df):
        raw = self._build_lstm_raw(df)
        scaled = self.scaler.transform(raw)
        xs, _ = _crear_secuencias(scaled)
        mse = self._recon_mse(xs)
        return (mse > self.threshold).astype(int)

    def predecir_hibrido(self, df):
        raw = self._build_lstm_raw(df)
        scaled = self.scaler.transform(raw)
        xs, end_idx = _crear_secuencias(scaled)
        mse = self._recon_mse(xs)

        X_hy = raw.iloc[end_idx].copy().reset_index(drop=True)
        X_hy['fe_lstm_mse'] = mse
        X_hy = X_hy[self.cfg['feature_columns_hybrid']]
        pred = self.xgb_hybrid.predict(X_hy)
        return self.le.inverse_transform(pred)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Inferencia MQTTDetector sobre un CSV (modelo hibrido)')
    ap.add_argument('model_dir', help='Directorio con los modelos exportados')
    ap.add_argument('csv', help='CSV con el mismo formato del entrenamiento')
    ap.add_argument('--device', default=None, help='cpu o cuda; por defecto autodetecta')
    args = ap.parse_args(argv)

    detector = MQTTDetector(args.model_dir, device=args.device)
    df = pd.read_csv(args.csv, low_memory=False)
    for label in detector.predecir_hibrido(df):
        print(label)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
