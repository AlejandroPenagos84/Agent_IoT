"""Perfil del tráfico normal por captura de origen y efecto en la regla trivial."""

from ..common import TARGET_COL, mqtt_port_masks, normal_frames, packet_types
from ..mqtt_proxy.analysis import score_rule


def normal_profile_by_capture(df):
    """Frames, conexiones, % MQTT, % PUBLISH y mediana de ``frame.len`` del normal."""
    import pandas as pd

    normal = normal_frames(df)
    capture = normal['_capture']
    src, dst = mqtt_port_masks(normal)
    return pd.DataFrame({
        'frames normales': capture.value_counts(),
        'conexiones normales': normal.groupby('_capture')['_connection'].nunique(),
        '% puerto MQTT': 100 * (src | dst).groupby(capture).mean(),
        '% capa MQTT': 100 * normal['mqtt.hdrflags'].notna().groupby(capture).mean(),
        '% PUBLISH': 100 * packet_types(normal).eq('PUBLISH').groupby(capture).mean(),
        'frame.len mediana': pd.to_numeric(normal['frame.len']).groupby(capture).median(),
    }).sort_index().round(2)


def normal_packet_types_by_capture(df):
    """% de cada tipo de paquete dentro del normal de cada captura."""
    import pandas as pd

    normal = normal_frames(df)
    table = (100 * pd.crosstab(packet_types(normal), normal['_capture'],
                               normalize='columns')).round(3)
    return table.sort_values(table.columns[0], ascending=False)


def port_rule_by_scope(df, attack_capture='DoS'):
    """Regla "puerto MQTT => DoS" con solo la captura de ataque y con la mezcla."""
    import pandas as pd

    src, dst = mqtt_port_masks(df)
    uses_port = src | dst
    is_attack = df[TARGET_COL].ne('normal')
    scopes = {
        f'solo {attack_capture}.csv': df['_capture'].eq(attack_capture),
        f'{attack_capture}.csv + normal de las demás': df['_capture'].notna(),
    }
    rows = [{
        'datos': name, 'frames': int(mask.sum()),
        '% DoS': round(100 * is_attack[mask].mean(), 2),
        **{k: v for k, v in score_rule(is_attack[mask], uses_port[mask]).items()
           if k != 'accuracy'},
    } for name, mask in scopes.items()]
    return pd.DataFrame(rows).set_index('datos').round(4)
