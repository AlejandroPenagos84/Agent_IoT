from __future__ import annotations

import argparse

from .pipeline import AlertProcessingPipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Validate and normalize persisted alert JSONL files.')
    parser.add_argument('--input', required=True, help='JSONL file or directory')
    parser.add_argument('--output', required=True, help='Output directory')
    args = parser.parse_args()
    report = AlertProcessingPipeline(args.input, args.output).run()
    print(
        f'Procesadas: {report.input_records}; válidas: {report.valid_records}; '
        f'inválidas: {report.invalid_records}; duplicadas: '
        f'{report.duplicate_records}')


if __name__ == '__main__':
    main()
