"""Age-based cleanup for evidence folders and daily alert files."""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATE_FORMAT = '%Y-%m-%d'


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_day(value: str) -> date | None:
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        return None


def prune_evidence(root: str | Path, retention_days: int,
                   today: date | None = None) -> list[Path]:
    """Delete ``YYYY-MM-DD`` evidence folders older than ``retention_days``."""
    if retention_days <= 0:
        return []
    folder = Path(root)
    if not folder.is_dir():
        return []
    cutoff = (today or _today()) - timedelta(days=retention_days)
    removed = []
    for child in sorted(folder.iterdir()):
        if not child.is_dir():
            continue
        day = _parse_day(child.name)
        if day is None or day >= cutoff:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed.append(child)
    return removed


def prune_daily_alerts(directory: str | Path, retention_days: int,
                       today: date | None = None) -> list[Path]:
    """Delete ``YYYY-MM-DD.jsonl`` daily alerts older than ``retention_days``."""
    if retention_days <= 0:
        return []
    folder = Path(directory)
    if not folder.is_dir():
        return []
    cutoff = (today or _today()) - timedelta(days=retention_days)
    removed = []
    for child in sorted(folder.glob('*.jsonl')):
        if not child.is_file():
            continue
        day = _parse_day(child.stem)
        if day is None or day >= cutoff:
            continue
        child.unlink()
        removed.append(child)
    return removed


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description='Delete evidence and daily alert files past their retention.')
    parser.add_argument('--evidence-dir', default=os.getenv('EVIDENCE_DIR', '/evidence'))
    parser.add_argument('--evidence-retention-days', type=int,
                        default=_env_int('EVIDENCE_RETENTION_DAYS', 30))
    parser.add_argument('--alert-dir', default=os.getenv('ALERT_DIR', '/alerts'))
    parser.add_argument('--alert-retention-days', type=int,
                        default=_env_int('ALERT_RETENTION_DAYS', 0))
    args = parser.parse_args(argv)
    evidence = prune_evidence(args.evidence_dir, args.evidence_retention_days)
    alerts = prune_daily_alerts(args.alert_dir, args.alert_retention_days)
    print(f'Retención: {len(evidence)} carpetas de evidencia y '
          f'{len(alerts)} archivos de alertas borrados')


if __name__ == '__main__':
    main()
