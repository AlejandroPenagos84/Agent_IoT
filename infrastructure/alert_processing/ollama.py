"""Generate a natural-language report from an analytical JSON report."""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

REPORT_PROMPT = """Actúa como analista de seguridad IoT y MQTT, especializado
en interpretar estadísticas de tráfico y alertas.

Analiza el JSON y redacta un informe claro y suficientemente detallado en
español que explique qué ocurrió durante el periodo, qué comportamientos
destacan y qué situaciones requieren atención.

No describas la estructura del JSON ni enumeres sus campos. Relaciona las
estadísticas para identificar concentraciones de actividad, comportamientos
recurrentes y posibles anomalías. Explica la importancia de los patrones
encontrados, no solo sus valores.

Distingue los hechos observados de las posibles interpretaciones. No inventes
eventos, causas ni conclusiones. Una cantidad elevada de alertas no confirma por
sí sola un ataque.

Utiliza lenguaje natural, profesional y directo. Prefiere párrafos cortos y
conserva los identificadores técnicos relevantes. Incluye, cuando sean
significativos, los nombres de los tópicos, las IP, los clientes, los tipos de
alerta y las ventanas temporales concretas. Explica por qué esos elementos son
relevantes, sin convertir el informe en un inventario. Evita repetir cifras o
incluir información irrelevante.

Organiza el informe con hasta tres encabezados, según la información disponible:

## Resumen
## Hallazgos
## Recomendaciones

Escribe únicamente el informe final, exclusivamente en español. Desarrolla las
tres secciones con la información disponible y termina siempre la sección de
recomendaciones con frases completas. No interrumpas el informe, no lo dejes
inconcluso y no termines a mitad de una frase.

DATOS DE ENTRADA (no los repitas en la respuesta):
"""


def generate_report(
    report: dict[str, Any],
    *,
    base_url: str,
    model: str,
    timeout: float = 120.0,
    print_stream: bool = True,
) -> str:
    """Ask Ollama to turn a JSON report into a natural-language report."""
    if not base_url.strip():
        raise ValueError("Ollama base URL cannot be empty")
    if not model.strip():
        raise ValueError("Ollama model cannot be empty")

    system = (
        "Redactas informes ejecutivos de seguridad. Responde exclusivamente en "
        "español. Interpreta los datos y escribe un informe completo y "
        "moderadamente detallado. Nunca "
        "devuelvas JSON, código, bloques ``` ni una copia de los datos de "
        "entrada; devuelve únicamente prosa y encabezados Markdown."
    )
    user_prompt = (
        REPORT_PROMPT
        + "\n--- INICIO DE DATOS ---\n"
        + json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n--- FIN DE DATOS ---\n\n"
        + "Ahora redacta el informe final. No repitas los datos de entrada."
    )

    def request_chat(user_content: str) -> str:
        payload = {
            "model": model,
            "messages": [
            {
                "role": "system",
                "content": system,
            },
            {
                "role": "user",
                "content": user_content,
            },
            ],
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_predict": 1200,
            },
        }
        request = Request(
            f"{base_url.rstrip('/')}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                parts: list[str] = []
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    result = json.loads(line)
                    message = result.get("message")
                    text = message.get("content") if isinstance(message, dict) else None
                    if isinstance(text, str):
                        parts.append(text)
                        if print_stream:
                            print(text, end="", flush=True)
                if print_stream:
                    print(file=sys.stdout)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama returned HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not connect to Ollama: {exc.reason}") from exc

        text = "".join(parts)
        if not text.strip():
            raise RuntimeError("Ollama response did not contain a non-empty 'content'")
        text = text.strip()
        if _looks_like_json(text):
            raise RuntimeError(
                "Ollama returned the input data instead of a natural-language report"
            )
        return text

    return request_chat(user_prompt)


def _looks_like_json(text: str) -> bool:
    """Detect JSON or a fenced JSON response instead of prose."""
    candidate = text.strip()
    if candidate.startswith("```json") and candidate.endswith("```"):
        return True
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, (dict, list))
