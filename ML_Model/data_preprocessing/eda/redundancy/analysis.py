"""Columnas derivables de mqtt.hdrflags (motivo REDUNDANT), verificadas bit a bit."""

from ..common import MQTT_ANY, NO_MQTT, packet_types, parse_hdrflags

# Bits de mqtt.hdrflags que tshark también expone como columnas separadas:
# columna -> (desplazamiento, máscara, tipos donde el campo tiene significado).
# DUP/QoS/RETAIN solo están definidos para PUBLISH en MQTT 3.1.1.
HDRFLAGS_FIELDS = {
    'mqtt.msgtype': (4, 0xF, MQTT_ANY), 'mqtt.dupflag': (3, 0x1, 'PUBLISH'),
    'mqtt.qos': (1, 0x3, 'PUBLISH'), 'mqtt.retain': (0, 0x1, 'PUBLISH'),
}


def hdrflags_redundancy(df, columns=tuple(HDRFLAGS_FIELDS)):
    """Comprueba que cada columna se obtiene bit a bit de mqtt.hdrflags.

    ``mismatches_in_scope`` cuenta discrepancias donde el campo tiene significado
    (PUBLISH para DUP/QoS/RETAIN); ``mismatches_out_of_scope`` y
    ``out_of_scope_types`` registran el resto, donde tshark rellena el campo
    aunque esos bits no tengan ese significado.
    """
    import pandas as pd

    flags = parse_hdrflags(df['mqtt.hdrflags'])
    types = packet_types(df)
    rows = []
    for column in columns:
        shift, mask, scope = HDRFLAGS_FIELDS[column]
        observed = pd.to_numeric(df[column], errors='coerce')
        both = observed.notna() & flags.notna()
        derived = (flags[both].to_numpy(dtype=int) >> shift) & mask
        bad = pd.Series(False, index=df.index)
        bad[both] = derived != observed[both].to_numpy(dtype=int)
        in_scope = types.ne(NO_MQTT) if scope == MQTT_ANY else types.eq(scope)
        outside = types[bad & ~in_scope].value_counts()
        rows.append({
            'column': column, 'source': 'mqtt.hdrflags',
            'bits': f'{shift + mask.bit_length() - 1}-{shift}', 'scope': scope,
            'compared_in_scope': int((both & in_scope).sum()),
            'mismatches_in_scope': int((bad & in_scope).sum()),
            'mismatches_out_of_scope': int((bad & ~in_scope).sum()),
            'out_of_scope_types': ', '.join(f'{k}={v}' for k, v in outside.items()) or '-',
            'only_in_derived': int((observed.notna() & flags.isna()).sum()),
        })
    return pd.DataFrame(rows, columns=[
        'column', 'source', 'bits', 'scope', 'compared_in_scope', 'mismatches_in_scope',
        'mismatches_out_of_scope', 'out_of_scope_types', 'only_in_derived',
    ]).set_index('column')
