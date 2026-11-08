import pandas as pd
import numpy as np

TARGET_COL = 'type'
LABEL_MAP = {'dos': 'DoS', 'normal': 'normal'}
FLOW_COLUMNS = ['ip.src', 'tcp.srcport', 'ip.dst', 'tcp.dstport']
NUMERIC_COLUMNS = ['tcp.srcport', 'tcp.dstport', 'frame.time_epoch', 'mqtt.msgtype']
REQUIRED_COLUMNS = FLOW_COLUMNS + [
    'frame.time_epoch', 'frame.time_delta', 'frame.len',
    'mqtt.msgtype', TARGET_COL,
]
STRING_DTYPES = {
    'mqtt.msg': 'string', 'mqtt.topic': 'string',
    'ip.src': 'string', 'ip.dst': 'string',
}


# Read one capture.
def read_capture(path):
    return pd.read_csv(path, low_memory=False, dtype=STRING_DTYPES)


# Validate the required schema and normalize frame-level labels.
# only_labels keeps just those raw labels (e.g. {'normal'}) before validating,
# so a capture of another attack can contribute only its normal traffic.
def normalize_schema(data, capture, only_labels=None):
    if 'Type' in data.columns and TARGET_COL not in data.columns:
        data = data.rename(columns={'Type': TARGET_COL})

    missing = set(REQUIRED_COLUMNS) - set(data.columns)
    if missing:
        raise ValueError(f'{capture}: missing required columns {sorted(missing)}')

    labels = data[TARGET_COL].astype(str).str.strip().str.lower()
    if only_labels is not None:
        keep = labels.isin(only_labels)
        print(f'{capture}: kept labels {sorted(only_labels)}; '
              f'discarded {labels[~keep].value_counts().to_dict()}')
        data, labels = data.loc[keep], labels[keep]
    unknown = labels[~labels.isin(LABEL_MAP)].unique()
    if len(unknown):
        raise ValueError(f'{capture}: unknown labels {unknown}')

    data = data.copy()
    data[TARGET_COL] = labels.map(LABEL_MAP)
    return data


# Convert fields used by filtering and connection grouping.
def coerce_numeric(data, columns=NUMERIC_COLUMNS):
    data = data.copy()
    for col in columns:
        data[col] = pd.to_numeric(data[col], errors='coerce')
    return data


# Select IPv4/TCP frames with complete, valid endpoints.
def filter_valid_flows(data):
    data = data.dropna(subset=FLOW_COLUMNS + ['frame.time_epoch'])
    valid = (
        data['ip.src'].str.strip().ne('') & data['ip.dst'].str.strip().ne('')
        & data['tcp.srcport'].between(1, 65535)
        & data['tcp.dstport'].between(1, 65535)
        & data['tcp.srcport'].mod(1).eq(0) & data['tcp.dstport'].mod(1).eq(0)
        & np.isfinite(data['frame.time_epoch'])
    )
    data = data.loc[valid].copy()
    data['_original_row'] = data.index
    return data


# Build connection and direction keys before dropping identifier columns.
def add_session_keys(data, capture):
    data = data.sort_values('frame.time_epoch', kind='stable').copy()
    data['_capture'] = capture

    rows = list(data[FLOW_COLUMNS].itertuples(index=False, name=None))
    endpoints = [
        tuple(sorted(((str(s), int(sp)), (str(d), int(dp)))))
        for s, sp, d, dp in rows
    ]
    data['_endpoints'] = pd.Series(endpoints, index=data.index, dtype=object)

    # Without tcp.stream, each new CONNECT starts another session for the same endpoints.
    connect = data['mqtt.msgtype'].eq(1).astype(int)
    session = connect.groupby(data['_endpoints'], sort=False).cumsum()

    connections = [(capture, ep, int(n)) for ep, n in zip(endpoints, session)]
    data['_connection'] = connections
    data['_direction'] = [
        (conn, str(s), int(sp), str(d), int(dp))
        for conn, (s, sp, d, dp) in zip(connections, rows)
    ]
    return data


# Process one capture.
def load_capture(capture, path, only_labels=None):
    data = read_capture(path)
    data = normalize_schema(data, capture, only_labels)
    data = coerce_numeric(data)
    print(f'{capture}: all frames: {data[TARGET_COL].value_counts().to_dict()}')

    before = len(data)
    data = filter_valid_flows(data)
    print(f'{capture}: excluded due to invalid network context: {before - len(data)}')

    data = add_session_keys(data, capture)
    print(f'{capture}: selected IPv4/TCP frames: {data[TARGET_COL].value_counts().to_dict()}')
    return data


# Merge processed captures. Captures listed in normal_only contribute only
# their normal frames (their attack labels are discarded, not relabeled).
# _connection includes the capture name, so sessions never span files.
def load_and_merge(files, normal_only=()):
    unknown = set(normal_only) - set(files)
    if unknown:
        raise ValueError(f'normal_only names unknown captures: {sorted(unknown)}')
    frames = [
        load_capture(capture, path, {'normal'} if capture in normal_only else None)
        for capture, path in files.items()
    ]
    if not frames:
        raise ValueError('No capture files were provided')
    merged = pd.concat(frames, ignore_index=True)
    if merged.empty:
        raise ValueError('No IPv4/TCP frames with complete endpoints were found')
    return merged
