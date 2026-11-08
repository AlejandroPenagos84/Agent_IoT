"""Política de descarte de columnas para la detección binaria DoS vs normal.

Cada columna capturada recibe semántica, motivo, acción y justificación. Los
motivos dependientes de los datos (EMPTY, CONSTANT, DUPLICATE, STRUCTURAL_NULL)
se calculan con las funciones de ``eda``; los semánticos (LEAKAGE, RAW_TEXT,
REDUNDANT, BEHAVIOR) se declaran aquí. Ninguna decisión usa el % global de nulos.
"""

from .eda import (
    MQTT_ANY, duplicate_columns, hdrflags_redundancy, packet_type_separation,
    structural_null_alignment,
)
from .feature_engineering import INTERNAL_COLUMNS

MOTIVES = [
    'EMPTY', 'CONSTANT', 'DUPLICATE', 'REDUNDANT', 'LEAKAGE',
    'STRUCTURAL_NULL', 'RAW_TEXT', 'BEHAVIOR',
]
ACTIONS = ['DROP', 'KEEP', 'DERIVE']

# Qué significa cada campo de tshark. Una columna sin semántica hace fallar la
# política: no se descarta nada sin escribir qué es.
SEMANTICS = {
    # Tiempo y orden de captura
    'frame.time_delta': 'segundos desde el frame capturado anterior',
    'frame.time_delta_displayed': 'segundos desde el frame mostrado anterior en tshark',
    'frame.time_epoch': 'instante absoluto de captura (Unix epoch)',
    'frame.time_invalid': 'marca de timestamp inválido',
    'frame.time_relative': 'segundos desde el primer frame de la captura',
    'frame.number': 'número de orden del frame en el archivo',
    # Identidad de red
    'ip.src': 'dirección IP de origen',
    'ip.dst': 'dirección IP de destino',
    'eth.src': 'MAC de origen',
    'eth.dst': 'MAC de destino',
    'tcp.srcport': 'puerto TCP de origen',
    'tcp.dstport': 'puerto TCP de destino',
    # Metadatos del frame
    'frame.len': 'bytes del frame en el cable',
    'frame.cap_len': 'bytes del frame guardados en la captura',
    'frame.coloring_rule.name': 'nombre de la regla de color de Wireshark',
    'frame.coloring_rule.string': 'filtro de la regla de color de Wireshark',
    'frame.comment': 'comentario manual del frame',
    'frame.comment.expert': 'aviso experto sobre el comentario',
    'frame.encap_type': 'tipo de encapsulado de capa 2',
    'frame.file_off': 'offset del frame dentro del archivo',
    'frame.ignored': 'frame marcado como ignorado en Wireshark',
    'frame.incomplete': 'frame truncado en la captura',
    'frame.interface_id': 'id de la interfaz de captura',
    'frame.interface_name': 'nombre de la interfaz de captura',
    'frame.link_nr': 'número de enlace de captura',
    'frame.marked': 'frame marcado manualmente en Wireshark',
    'frame.md5_hash': 'hash MD5 del frame',
    'frame.offset_shift': 'corrección de tiempo aplicada al frame',
    # MQTT: cabecera fija
    'mqtt.hdrflags': 'byte de cabecera fija MQTT (tipo, DUP, QoS, RETAIN)',
    'mqtt.msgtype': 'tipo de paquete MQTT (bits 7-4 de hdrflags)',
    'mqtt.dupflag': 'bandera DUP de reenvío (bit 3 de hdrflags)',
    'mqtt.qos': 'nivel QoS del PUBLISH (bits 2-1 de hdrflags)',
    'mqtt.retain': 'bandera RETAIN (bit 0 de hdrflags)',
    'mqtt.len': 'longitud restante del paquete MQTT',
    # MQTT: CONNECT
    'mqtt.clientid': 'identificador del cliente MQTT (solo CONNECT)',
    'mqtt.clientid_len': 'longitud del client_id (solo CONNECT)',
    'mqtt.conflags': 'byte de banderas de CONNECT',
    'mqtt.conflag.cleansess': 'bandera clean session (solo CONNECT)',
    'mqtt.conflag.passwd': 'bandera de contraseña presente (solo CONNECT)',
    'mqtt.conflag.qos': 'QoS del will message (solo CONNECT)',
    'mqtt.conflag.reserved': 'bit reservado de CONNECT',
    'mqtt.conflag.retain': 'retain del will message (solo CONNECT)',
    'mqtt.conflag.uname': 'bandera de usuario presente (solo CONNECT)',
    'mqtt.conflag.willflag': 'bandera de will message (solo CONNECT)',
    'mqtt.kalive': 'keepalive del cliente en segundos (solo CONNECT)',
    'mqtt.proto_len': 'longitud del nombre del protocolo (solo CONNECT)',
    'mqtt.protoname': 'nombre del protocolo, "MQTT" (solo CONNECT)',
    'mqtt.ver': 'versión del protocolo MQTT (solo CONNECT)',
    'mqtt.username': 'usuario (solo CONNECT)',
    'mqtt.username_len': 'longitud del usuario (solo CONNECT)',
    'mqtt.passwd': 'contraseña (solo CONNECT)',
    'mqtt.passwd_len': 'longitud de la contraseña (solo CONNECT)',
    'mqtt.willmsg': 'will message (solo CONNECT)',
    'mqtt.willmsg_len': 'longitud del will message (solo CONNECT)',
    'mqtt.willtopic': 'topic del will message (solo CONNECT)',
    'mqtt.willtopic_len': 'longitud del topic del will (solo CONNECT)',
    # MQTT: CONNACK, PUBLISH, SUBSCRIBE
    'mqtt.conack.flags': 'byte de banderas de CONNACK',
    'mqtt.conack.flags.reserved': 'bits reservados de CONNACK',
    'mqtt.conack.flags.sp': 'session present (solo CONNACK)',
    'mqtt.conack.val': 'código de retorno de CONNACK',
    'mqtt.msgid': 'packet identifier (PUBLISH QoS>0, PUBACK, PUBREL...)',
    'mqtt.msg': 'payload del PUBLISH',
    'mqtt.topic': 'topic del PUBLISH',
    'mqtt.topic_len': 'longitud del topic del PUBLISH',
    'mqtt.sub.qos': 'QoS solicitado en SUBSCRIBE',
    'mqtt.suback.qos': 'QoS concedido en SUBACK',
}

# Decisiones por significado: no dependen de las estadísticas de la captura.
LEAKAGE = {
    'ip.src': 'identifica al host, no el comportamiento',
    'ip.dst': 'identifica al host, no el comportamiento',
    'eth.src': 'identifica la interfaz física, no el comportamiento',
    'eth.dst': 'identifica la interfaz física, no el comportamiento',
    'mqtt.clientid': 'identifica al cliente concreto; memorizarlo no generaliza',
    'frame.time_epoch': 'fecha de captura; solo se usa como contexto para ordenar ventanas',
    'frame.time_relative': 'momento dentro de la captura; separa por cuándo se grabó el ataque',
    'frame.number': 'orden en el archivo; equivale a un reloj de captura',
}
# Puertos: el valor crudo es leakage (puerto efímero); se derivan banderas.
LEAKAGE_DERIVE = {
    'tcp.srcport': 'puerto efímero; solo se deriva fe_is_broker_to_client (origen 1883/8883)',
    'tcp.dstport': 'puerto efímero; solo se deriva fe_is_standard_mqtt_port (destino 1883/8883)',
}
RAW_TEXT = {
    'mqtt.msg': 'texto crudo de aplicación; se resume en fe_msg_entropy',
    'mqtt.topic': 'texto crudo de aplicación; se resume en fe_topic_entropy y fe_topic_depth',
}
# Columna derivada -> columna de la que sale. Se verifica bit a bit con los datos.
REDUNDANT = {
    'mqtt.msgtype': 'mqtt.hdrflags',
    'mqtt.dupflag': 'mqtt.hdrflags',
    'mqtt.qos': 'mqtt.hdrflags',
    'mqtt.retain': 'mqtt.hdrflags',
}
# Entradas del modelo. Las MQTT son nulas fuera de MQTT/PUBLISH: el nulo se
# codifica con el centinela -1 ("no aplica"), fuera del dominio (>= 0), no se imputa.
KEEP = {
    'frame.len': ('BEHAVIOR', 'tamaño de frame; las ráfagas DoS desplazan su distribución'),
    'frame.time_delta': ('BEHAVIOR', 'ritmo entre frames; la inundación DoS lo acorta'),
    'mqtt.hdrflags': ('STRUCTURAL_NULL',
                      'tipo de paquete y banderas; nulo = frame sin MQTT, centinela -1'),
    'mqtt.len': ('STRUCTURAL_NULL',
                 'tamaño del paquete MQTT; nulo = frame sin MQTT, centinela -1'),
    'mqtt.topic_len': ('STRUCTURAL_NULL',
                       'tamaño del topic; nulo = no es PUBLISH, centinela -1'),
}
# Al elegir qué columna conservar entre duplicadas, se prefieren las del modelo.
PREFERRED_COLUMNS = list(KEEP)


def _fmt(value):
    """Valor legible para la justificación (sin np.float64(...))."""
    if isinstance(value, str):
        return repr(value)
    value = float(value)
    return str(int(value)) if value.is_integer() else f'{value:g}'


def _semantic_decision(column):
    if column in LEAKAGE:
        return 'LEAKAGE', 'DROP', LEAKAGE[column]
    if column in LEAKAGE_DERIVE:
        return 'LEAKAGE', 'DERIVE', LEAKAGE_DERIVE[column]
    if column in RAW_TEXT:
        return 'RAW_TEXT', 'DERIVE', RAW_TEXT[column]
    if column in KEEP:
        motive, why = KEEP[column]
        return motive, 'KEEP', why
    return None


def _structural_decision(row, separation):
    """Pasos 1-4 de la regla STRUCTURAL_NULL para una columna parcialmente nula."""
    group = row['best_group']
    if not row['aligned']:
        return 'DROP', (
            f"paso 1 falla: solo {row['precision']:.0%} de sus no nulos son {group} "
            f"(resto: {row['non_null_by_type']}); mezcla tipos de paquete, la presencia "
            f'de cada tipo ya la codifica mqtt.hdrflags')
    sep = separation.loc[group]
    evidence = (f"{group}: {sep['pct_normal']:.3f}% de frames normal vs "
                f"{sep['pct_attack']:.3f}% DoS")
    if not sep['separates']:
        return 'DROP', f'no discrimina DoS ({evidence})'
    return 'DERIVE', (f'{group} sí separa ({evidence}); no se usa cruda, '
                      f'derivar nº de {group} por ventana o por _connection')


def build_column_policy(df, min_jaccard=0.95, min_ratio=2.0, min_count=10):
    """Tabla columna/semántica/motivo/acción/justificación sin celdas vacías.

    Orden de evaluación: EMPTY, decisiones semánticas, REDUNDANT verificada,
    CONSTANT, DUPLICATE y STRUCTURAL_NULL. Devuelve ``(policy, evidence)``,
    donde ``evidence`` agrupa las tablas que justifican cada decisión.
    """
    import pandas as pd

    columns = [name for name in df.columns if name not in INTERNAL_COLUMNS]
    missing_semantics = sorted(set(columns) - set(SEMANTICS))
    if missing_semantics:
        raise ValueError(f'Columns without documented semantics: {missing_semantics}')

    non_null = df[columns].notna().sum()
    n_unique = df[columns].nunique(dropna=True)
    duplicates = duplicate_columns(df, columns, preferred=PREFERRED_COLUMNS)
    redundancy = hdrflags_redundancy(df, [c for c in REDUNDANT if c in df.columns])
    partial = [c for c in columns if 0 < non_null[c] < len(df)]
    alignment = structural_null_alignment(df, partial, min_jaccard=min_jaccard)
    separation = packet_type_separation(df, min_ratio=min_ratio, min_count=min_count)

    rows = []
    for column in columns:
        values = df[column].dropna()
        semantic = _semantic_decision(column)
        if non_null[column] == 0:
            motive, action, why = 'EMPTY', 'DROP', 'sin ningún valor observado'
        elif semantic is not None:
            motive, action, why = semantic
        elif column in REDUNDANT:
            source = REDUNDANT[column]
            check = redundancy.loc[column]
            if check['mismatches_in_scope'] or check['only_in_derived']:
                raise ValueError(f'{column} is not derivable from {source}: {check.to_dict()}')
            motive, action = 'REDUNDANT', 'DROP'
            why = (f"se conserva {source}; 0 discrepancias en "
                   f"{int(check['compared_in_scope']):,} frames {check['scope']}")
            if check['mismatches_out_of_scope']:
                why += (f"; {int(check['mismatches_out_of_scope'])} difieren fuera de "
                        f"{check['scope']} ({check['out_of_scope_types']}), donde esos "
                        f"bits no significan DUP/QoS/RETAIN")
        elif n_unique[column] <= 1:
            value = _fmt(values.iloc[0])
            motive, action = 'CONSTANT', 'DROP'
            if column in partial:
                group = alignment.loc[column, 'best_group']
                why = (f"solo existe en {group} y siempre vale {value}: equivale a "
                       f"un indicador de {group}, ya presente en mqtt.hdrflags")
            else:
                why = f'único valor {value} en {len(values):,} filas; no aporta variación'
        elif column in duplicates.index:
            kept = duplicates.loc[column, 'duplicate_of']
            motive, action = 'DUPLICATE', 'DROP'
            why = f'idéntica a {kept} en el 100% de filas; se conserva {kept}'
        elif column in partial:
            motive = 'STRUCTURAL_NULL'
            action, why = _structural_decision(alignment.loc[column], separation)
        else:
            raise ValueError(f'{column}: no rule applies; document a decision for it')
        rows.append({
            'columna': column, 'semántica': SEMANTICS[column], 'motivo': motive,
            'acción': action, 'justificación frente a DoS': why,
        })

    policy = pd.DataFrame(rows)
    assert policy['motivo'].isin(MOTIVES).all()
    assert policy['acción'].isin(ACTIONS).all()
    assert policy.notna().all().all() and policy.astype(str).ne('').all().all()
    evidence = {
        'duplicates': duplicates, 'redundancy': redundancy,
        'alignment': alignment, 'separation': separation,
    }
    return policy, evidence


def apply_column_policy(df, policy, keep_context=()):
    """Elimina columnas DROP; conserva las indicadas como contexto (no features)."""
    dropped = policy.loc[policy['acción'].eq('DROP'), 'columna']
    to_drop = [c for c in dropped if c in df.columns and c not in set(keep_context)]
    return df.drop(columns=to_drop), to_drop
