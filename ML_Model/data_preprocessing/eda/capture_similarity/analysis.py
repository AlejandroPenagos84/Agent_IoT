"""¿El normal de las tres capturas es el mismo? Solo frames normales.

Cuatro vistas: numéricas (mediana/IQR y KS D), categóricas (Jensen-Shannon),
hosts (Jaccard de IP) y un clasificador que intenta adivinar la captura.
"""

from ..common import MQTT_PORTS, normal_frames, packet_types, parse_hdrflags, port_role

NUMERIC_COLUMNS = ['frame.len', 'frame.time_delta', 'mqtt.len', 'mqtt.topic_len']


def _pairs(sources):
    from itertools import combinations
    return list(combinations(sources, 2))


def _sources(normal):
    return sorted(normal['_capture'].unique())


def normal_numeric(df):
    """Columnas numéricas del normal, convertidas a float."""
    import pandas as pd

    normal = normal_frames(df)
    return pd.DataFrame({c: pd.to_numeric(normal[c], errors='coerce')
                         for c in NUMERIC_COLUMNS})


def numeric_summary_by_capture(df):
    """Mediana e IQR de cada columna numérica (solo valores observados)."""
    normal = normal_frames(df)
    numeric = normal_numeric(df)
    source = normal['_capture']
    summary = numeric.groupby(source).agg(['median', lambda s: s.quantile(.75) - s.quantile(.25)])
    summary.columns = [f'{col} {"mediana" if stat == "median" else "IQR"}'
                       for col, stat in summary.columns]
    summary['% con capa MQTT'] = 100 * numeric['mqtt.len'].notna().groupby(source).mean()
    return summary.round(5)


def ks_by_capture_pair(df):
    """Estadístico KS D por par de capturas (tamaño de efecto, no p-valor)."""
    import pandas as pd
    from scipy.stats import ks_2samp

    normal = normal_frames(df)
    numeric = normal_numeric(df)
    source = normal['_capture']
    return pd.DataFrame({
        f'{a} vs {b}': {c: ks_2samp(numeric.loc[source.eq(a), c].dropna(),
                                    numeric.loc[source.eq(b), c].dropna()).statistic
                        for c in numeric}
        for a, b in _pairs(_sources(normal))
    }).round(3)


def service_port(df):
    """Puerto de servicio: el menor del par si es conocido (<1024) o MQTT."""
    import pandas as pd

    ports = df[['tcp.srcport', 'tcp.dstport']].apply(pd.to_numeric, errors='coerce')
    low = ports.min(axis=1)
    return low.astype(int).astype(str).where(
        (low < 1024) | low.isin(MQTT_PORTS), 'efímero/otro').rename('puerto')


def _categorical(normal):
    return {
        'tipo de paquete': packet_types(normal),
        'rol del puerto': port_role(normal),
        'puerto de servicio': service_port(normal),
    }


def js_by_capture_pair(df):
    """Distancia de Jensen-Shannon por par de capturas para cada variable categórica."""
    import pandas as pd
    from scipy.spatial.distance import jensenshannon

    normal = normal_frames(df)
    source = normal['_capture']
    rows = {}
    for name, values in _categorical(normal).items():
        dist = pd.crosstab(values, source, normalize='columns')
        rows[name] = {f'{a} vs {b}': jensenshannon(dist[a], dist[b], base=2)
                      for a, b in _pairs(_sources(normal))}
    return pd.DataFrame(rows).T.round(3)


def top_service_ports(df, top=8):
    """Puertos de servicio más frecuentes (% de frames normales de cada captura)."""
    import pandas as pd

    normal = normal_frames(df)
    table = pd.crosstab(service_port(normal), normal['_capture'], normalize='columns') * 100
    return table.loc[table.max(axis=1).sort_values(ascending=False).index[:top]].round(2)


def host_overlap(df):
    """IP vistas en cada captura y su índice de Jaccard por pares."""
    import pandas as pd

    normal = normal_frames(df)
    source = normal['_capture']
    hosts = {name: set(normal.loc[source.eq(name), 'ip.src'])
             | set(normal.loc[source.eq(name), 'ip.dst']) for name in _sources(normal)}
    return pd.DataFrame([{
        'par': f'{a} vs {b}', 'IPs en A': len(hosts[a]), 'IPs en B': len(hosts[b]),
        'IPs compartidas': len(hosts[a] & hosts[b]),
        'Jaccard': round(len(hosts[a] & hosts[b]) / len(hosts[a] | hosts[b]), 3),
    } for a, b in _pairs(_sources(normal))]).set_index('par')


def origin_classifier(df, seed=42, n_splits=5):
    """Adivina la captura de cada frame normal (CV agrupada por conexión).

    Usa features de comportamiento, sin IP ni puertos crudos. Devuelve
    ``(balanced_accuracy, matriz de confusión normalizada por fila)``.
    """
    import pandas as pd
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict

    normal = normal_frames(df)
    sources = _sources(normal)
    ports = normal[['tcp.srcport', 'tcp.dstport']].apply(pd.to_numeric, errors='coerce')
    features = normal_numeric(df).fillna(-1).assign(
        hdrflags=parse_hdrflags(normal['mqtt.hdrflags']).fillna(-1),
        to_broker=ports['tcp.dstport'].isin(MQTT_PORTS).astype(int),
        from_broker=ports['tcp.srcport'].isin(MQTT_PORTS).astype(int),
    )
    target = normal['_capture'].to_numpy()
    groups = pd.factorize(normal['_connection'].map(str))[0]
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    predicted = cross_val_predict(
        HistGradientBoostingClassifier(max_iter=200, random_state=seed, class_weight='balanced'),
        features, target, groups=groups, cv=cv)
    bacc = balanced_accuracy_score(target, predicted)
    matrix = pd.DataFrame(
        confusion_matrix(target, predicted, labels=sources, normalize='true'),
        index=[f'real {s}' for s in sources], columns=[f'pred {s}' for s in sources]).round(3)
    return bacc, matrix
