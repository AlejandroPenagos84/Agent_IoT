"""XGBoost con hiperparámetros fijos (sin Optuna), igual para todos los sets."""

XGB_PARAMS = {
    'n_estimators': 300,
    'learning_rate': 0.05,
    'max_depth': 4,
    'min_child_weight': 2.0,
    'subsample': 0.9,
    'colsample_bytree': 0.9,
    'reg_lambda': 1.0,
    'objective': 'binary:logistic',
    'tree_method': 'hist',
    'eval_metric': 'logloss',
    'n_jobs': -1,
}


def make_xgb(seed=42):
    from xgboost import XGBClassifier
    return XGBClassifier(**XGB_PARAMS, random_state=seed)


def fit_balanced(features, labels, seed=42):
    """Entrena con ``sample_weight`` balanceado por clase."""
    from sklearn.utils.class_weight import compute_sample_weight

    model = make_xgb(seed)
    model.fit(features, labels, sample_weight=compute_sample_weight('balanced', labels))
    return model
