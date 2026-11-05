"""Generate a natural-language report from an analytical JSON report."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

REPORT_PROMPT = """Eres un analista especializado en seguridad de redes IoT y comunicaciones MQTT.

Tu tarea es analizar las estadísticas proporcionadas y generar un reporte periódico de actividad.

El reporte debe incluir:

1. Resumen general de la actividad.
2. Clientes con mayor cantidad de alertas.
3. Direcciones IP y tópicos con mayor actividad.
4. Patrones temporales relevantes.
5. Hallazgos y posibles comportamientos anómalos.
6. Conclusiones y recomendaciones.

Reglas:
- Utiliza exclusivamente la información proporcionada.
- No inventes estadísticas ni eventos.
- Diferencia los hechos observados de las posibles interpretaciones.
- No afirmes que existe un ataque confirmado únicamente por una cantidad elevada de alertas.
- Si los datos son insuficientes, indícalo.
- Evita repetir estadísticas innecesariamente.

Redacta todo el reporte exclusivamente en español. No uses inglés, aunque los
nombres de campos del JSON estén en inglés. Traduce los títulos, explicaciones,
hallazgos, conclusiones y recomendaciones. Si incluyes nombres técnicos,
conserva únicamente los identificadores, direcciones IP, tópicos y valores
originales necesarios.

La respuesta DEBE comenzar exactamente con:
## Resumen general

Usa exactamente estos encabezados, en este orden:
## Resumen general
## Clientes con más alertas
## IP y tópicos con mayor actividad
## Patrones temporales
## Hallazgos y posibles anomalías
## Conclusiones y recomendaciones

Escribe las explicaciones, títulos y viñetas en español. No escribas frases
como "Based on", "Summary", "Client", "Alert Count" o "If you need".

Estadísticas en JSON:
"""


def generate_report(
    report: dict[str, Any],
    *,
    base_url: str,
    model: str,
    timeout: float = 120.0,
) -> str:
    """Ask Ollama to turn a JSON report into a Spanish natural-language report."""
    if not base_url.strip():
        raise ValueError("Ollama base URL cannot be empty")
    if not model.strip():
        raise ValueError("Ollama model cannot be empty")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Responde exclusivamente en español. No escribas ninguna "
                    "sección ni frase en inglés. Usa Markdown con los seis "
                    "encabezados españoles indicados por el usuario y comienza "
                    "exactamente con '## Resumen general'."
                ),
            },
            {
                "role": "user",
                "content": REPORT_PROMPT
                + "\n"
                + json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            },
        ],
        "stream": False,
        "options": {"temperature": 0},
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to Ollama: {exc.reason}") from exc

    message = result.get("message") if isinstance(result, dict) else None
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Ollama response did not contain a non-empty 'response'")
    return text.strip()
