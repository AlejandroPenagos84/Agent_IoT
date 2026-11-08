"""Generate a natural-language Markdown report from report.json using Ollama."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .ollama import generate_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a natural-language report with Ollama"
    )
    parser.add_argument("--input", default="/processed/report.json")
    parser.add_argument(
        "--output",
        help="Optional Markdown output path. If omitted, only print the response.",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
    )
    parser.add_argument(
        "--ollama-model",
        default=os.getenv("OLLAMA_MODEL", "gemma3:4b"),
    )
    parser.add_argument("--ollama-timeout", type=float, default=300.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        raise FileNotFoundError(f"JSON report does not exist: {input_path}")
    report = json.loads(input_path.read_text(encoding="utf-8"))
    natural_report = generate_report(
        report,
        base_url=args.ollama_url,
        model=args.ollama_model,
        timeout=args.ollama_timeout,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.tmp")
        temporary.write_text(natural_report + "\n", encoding="utf-8")
        temporary.replace(output)
        print(f"\nReporte natural publicado: {output}")


if __name__ == "__main__":
    main()
