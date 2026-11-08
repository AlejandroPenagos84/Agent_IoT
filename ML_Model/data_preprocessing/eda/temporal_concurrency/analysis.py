"""Concurrencia temporal del normal con el ataque dentro de una captura."""

from ..common import NORMAL_LABEL, TARGET_COL, attack_label, mqtt_port_masks


def _capture_frames(df, capture):
    import pandas as pd

    frames = df[df['_capture'].eq(capture)]
    time = pd.to_numeric(frames['frame.time_epoch'], errors='coerce')
    src, dst = mqtt_port_masks(frames)
    return frames, time, src | dst


def attack_window(df, capture='DoS'):
    """``(inicio, fin)`` en epoch del primer y último frame de ataque."""
    frames, time, _ = _capture_frames(df, capture)
    attack = frames[TARGET_COL].eq(attack_label(df))
    return float(time[attack].min()), float(time[attack].max())


def temporal_table(df, capture='DoS'):
    """Frames normales y de ataque antes/durante/después de la ventana del ataque."""
    import pandas as pd

    frames, time, mqtt = _capture_frames(df, capture)
    attack_name = attack_label(df)
    attack = frames[TARGET_COL].eq(attack_name)
    normal = frames[TARGET_COL].eq(NORMAL_LABEL)
    start, end = attack_window(df, capture)
    windows = [('antes', time < start), ('durante', (time >= start) & (time <= end)),
               ('después', time > end), ('total', pd.Series(True, index=frames.index))]
    return pd.DataFrame([{
        'ventana': name,
        'normal_total': int((normal & mask).sum()),
        'normal_mqtt': int((normal & mask & mqtt).sum()),
        f'{attack_name}_total': int((attack & mask).sum()),
        f'{attack_name}_mqtt': int((attack & mask & mqtt).sum()),
    } for name, mask in windows]).set_index('ventana')


def concurrent_normal_share(df, capture='DoS'):
    """``(normal MQTT durante el ataque, normal MQTT total, fracción)``."""
    table = temporal_table(df, capture)
    during, total = int(table.loc['durante', 'normal_mqtt']), int(table.loc['total', 'normal_mqtt'])
    return during, total, (during / total if total else 0.0)
