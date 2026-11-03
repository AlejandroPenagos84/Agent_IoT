from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REQUIRED_FIELDS = ('ts', 'kind', 'label')
OPTIONAL_FIELDS = (
    'alert_id', 'run_id', 'client_id', 'ip', 'topic', 'mse', 'source')
KNOWN_KINDS = frozenset({'class'})
KNOWN_SOURCES = frozenset({'tshark', 'mqtt', 'classifier', 'agente'})
_SPACE_RE = re.compile(r'\s+')


@dataclass
class ProcessingReport:
    """Counters and quality information produced by one processing run."""

    input_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    duplicate_records: int = 0
    missing_fields: Counter[str] = field(default_factory=Counter)
    unknown_sources: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result['missing_fields'] = dict(self.missing_fields)
        result['unknown_sources'] = dict(self.unknown_sources)
        return result


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{field_name} must be a string')
    value = _SPACE_RE.sub(' ', value).strip()
    if not value:
        raise ValueError(f'{field_name} must not be empty')
    return value


def _timestamp(value: Any) -> tuple[Any, str]:
    if isinstance(value, bool):
        raise ValueError('ts must be an epoch number or ISO-8601 string')
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError('ts must be finite')
        instant = datetime.fromtimestamp(float(value), timezone.utc)
        return value, instant.isoformat(timespec='microseconds').replace('+00:00', 'Z')
    if isinstance(value, str):
        original = value
        candidate = value.strip()
        if candidate.endswith('Z'):
            candidate = candidate[:-1] + '+00:00'
        try:
            instant = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError('ts is not a valid ISO-8601 timestamp') from exc
        if instant.tzinfo is None:
            raise ValueError('ts ISO-8601 value must include a timezone')
        return original, instant.astimezone(timezone.utc).isoformat(
            timespec='microseconds').replace('+00:00', 'Z')
    raise ValueError('ts must be an epoch number or ISO-8601 string')


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _ip(value: Any) -> str | None:
    if value is None:
        return None
    candidate = _text(value, 'ip')
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError as exc:
        raise ValueError('ip is not a valid IPv4 or IPv6 address') from exc


def _mse(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('mse must be numeric')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('mse must be numeric') from exc
    if not math.isfinite(result):
        raise ValueError('mse must be finite')
    return result


def _stable_alert_id(record: dict[str, Any]) -> str:
    canonical = json.dumps(
        {key: record.get(key) for key in (
            'ts_utc', 'kind', 'label', 'client_id', 'ip', 'topic',
            'mse', 'source', 'run_id')},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return f'generated:{hashlib.sha256(canonical.encode()).hexdigest()}'


class AlertProcessingPipeline:
    """Validate, normalize, deduplicate, and persist alert JSONL records."""

    def __init__(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        *,
        known_kinds: Iterable[str] = KNOWN_KINDS,
        known_sources: Iterable[str] = KNOWN_SOURCES,
    ) -> None:
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.known_kinds = frozenset(known_kinds)
        self.known_sources = frozenset(known_sources)

    def _files(self) -> list[Path]:
        if self.input_path.is_file():
            return [self.input_path]
        if self.input_path.is_dir():
            return sorted(self.input_path.glob('*.jsonl'))
        raise FileNotFoundError(f'Input path does not exist: {self.input_path}')

    def _normalize(self, raw: dict[str, Any], source_file: str,
                   source_line: int, report: ProcessingReport) -> dict[str, Any]:
        for field_name in REQUIRED_FIELDS:
            if field_name not in raw:
                report.missing_fields[field_name] += 1
                raise ValueError(f'missing required field: {field_name}')
        for field_name in OPTIONAL_FIELDS:
            if field_name not in raw or raw[field_name] is None:
                report.missing_fields[field_name] += 1

        original_ts, ts_utc = _timestamp(raw['ts'])
        kind = _text(raw['kind'], 'kind')
        if kind not in self.known_kinds:
            raise ValueError(f'unknown kind: {kind}')
        label = _text(raw['label'], 'label')
        source = _optional_text(raw.get('source'), 'source')
        if source is not None and source not in self.known_sources:
            report.unknown_sources[source] += 1

        normalized = {
            'alert_id': _optional_text(raw.get('alert_id'), 'alert_id'),
            'run_id': _optional_text(raw.get('run_id'), 'run_id'),
            'ts_original': original_ts,
            'ts_utc': ts_utc,
            'kind': kind,
            'label': label,
            'client_id': _optional_text(raw.get('client_id'), 'client_id'),
            'ip': _ip(raw.get('ip')),
            'topic': _optional_text(raw.get('topic'), 'topic'),
            'mse': _mse(raw.get('mse')),
            'source': source,
            'source_file': source_file,
            'source_line': source_line,
        }
        if normalized['alert_id'] is None:
            normalized['alert_id'] = _stable_alert_id(normalized)
            normalized['alert_id_origin'] = 'generated'
        else:
            normalized['alert_id_origin'] = 'provided'
        normalized['run_id_missing'] = normalized['run_id'] is None
        return normalized

    def run(self) -> ProcessingReport:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report = ProcessingReport()
        errors_path = self.output_dir / 'processing_errors.jsonl'
        duplicates_path = self.output_dir / 'duplicates.jsonl'
        records: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        with errors_path.open('w', encoding='utf-8') as errors, \
                duplicates_path.open('w', encoding='utf-8') as duplicates:
            for path in self._files():
                with path.open('r', encoding='utf-8', errors='replace') as handle:
                    for line_number, line in enumerate(handle, 1):
                        if not line.strip():
                            continue
                        report.input_records += 1
                        try:
                            raw = json.loads(line)
                            if not isinstance(raw, dict):
                                raise ValueError('JSON record must be an object')
                            record = self._normalize(
                                raw, str(path), line_number, report)
                        except (json.JSONDecodeError, ValueError, OverflowError) as exc:
                            report.invalid_records += 1
                            errors.write(json.dumps({
                                'source_file': str(path),
                                'source_line': line_number,
                                'error_type': 'invalid_json' if isinstance(
                                    exc, json.JSONDecodeError) else 'invalid_record',
                                'message': str(exc),
                                'raw_line': line.rstrip('\n'),
                            }, ensure_ascii=False) + '\n')
                            continue
                        previous = seen.get(record['alert_id'])
                        if previous is not None:
                            report.duplicate_records += 1
                            duplicates.write(json.dumps({
                                'alert_id': record['alert_id'],
                                'source_file': str(path),
                                'source_line': line_number,
                                'duplicate_of': previous,
                                'reason': 'same_alert_id',
                            }, ensure_ascii=False) + '\n')
                            continue
                        seen[record['alert_id']] = {
                            'source_file': record['source_file'],
                            'source_line': record['source_line'],
                        }
                        records.append(record)
                        report.valid_records += 1

        self._write_parquet(records)
        (self.output_dir / 'processing_report.json').write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
        return report

    def _write_parquet(self, records: list[dict[str, Any]]) -> None:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError(
                'Parquet output requires pandas and pyarrow. '
                'Install dependencies from requirements.txt.') from exc
        try:
            pd.DataFrame(records).to_parquet(
                self.output_dir / 'alerts.parquet', index=False, engine='pyarrow')
        except (ImportError, ValueError) as exc:
            raise RuntimeError(
                'Parquet output requires pyarrow. Install dependencies from '
                'requirements.txt.') from exc
