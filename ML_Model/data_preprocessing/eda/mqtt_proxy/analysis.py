"""¿MQTT = DoS? Composición de clase por grupo y reglas triviales sin modelo."""

from ..common import TARGET_COL, attack_label, mqtt_port_masks, port_role


def mqtt_proxy_table(df):
    """% de cada clase dentro de cada grupo (rol del puerto x capa MQTT).

    Es ``P(clase | grupo)``: la inversa de ``port_role_by_class``.
    """
    import pandas as pd

    layer = df['mqtt.hdrflags'].notna().map({True: 'con capa MQTT', False: 'sin capa MQTT'})
    counts = pd.crosstab([port_role(df), layer.rename('capa')], df[TARGET_COL])
    table = (100 * counts.div(counts.sum(axis=1), axis=0)).round(2).add_prefix('% ')
    table.insert(0, 'frames', counts.sum(axis=1))
    table.insert(1, '% del total', (100 * table['frames'] / len(df)).round(2))
    return table


def trivial_rules(df):
    """Reglas que predicen el ataque solo por la presencia de MQTT."""
    src, dst = mqtt_port_masks(df)
    has_layer = df['mqtt.hdrflags'].notna()
    return {
        'puerto MQTT => DoS': src | dst,
        'cliente -> broker => DoS': dst,
        'capa MQTT => DoS': has_layer,
        'puerto MQTT y capa MQTT => DoS': (src | dst) & has_layer,
    }


def score_rule(actual, predicted):
    """Métricas binarias de una regla (``actual`` y ``predicted`` booleanos)."""
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score,
                                 precision_score, recall_score)

    return {
        'accuracy': accuracy_score(actual, predicted),
        'balanced_accuracy': balanced_accuracy_score(actual, predicted),
        'precision_DoS': precision_score(actual, predicted, zero_division=0),
        'recall_DoS': recall_score(actual, predicted, zero_division=0),
        'macro_f1': f1_score(actual, predicted, average='macro', zero_division=0),
    }


def trivial_rule_baseline(df):
    """Una fila por regla trivial con sus métricas frente a la etiqueta real."""
    import pandas as pd

    is_attack = df[TARGET_COL].eq(attack_label(df))
    rows = [{'regla': name, **score_rule(is_attack, predicted)}
            for name, predicted in trivial_rules(df).items()]
    return pd.DataFrame(rows).set_index('regla').round(4)
