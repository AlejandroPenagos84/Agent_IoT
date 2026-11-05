import json
import unittest
from unittest.mock import patch
from urllib.request import Request

from infrastructure.alert_processing.ollama import REPORT_PROMPT, generate_report


class OllamaReportTests(unittest.TestCase):
    @patch("infrastructure.alert_processing.ollama.urlopen")
    def test_sends_json_and_prompt_to_chat_endpoint(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        response.read.return_value = json.dumps({
            "message": {"content": "Reporte listo"}
        }).encode()
        response.__iter__.return_value = iter(())
        with patch(
            "infrastructure.alert_processing.ollama.json.load",
            return_value={"message": {"content": "Reporte listo"}},
        ):
            result = generate_report(
                {"general": {"total_alerts": 2}},
                base_url="http://ollama:11434",
                model="qwen2.5:3b",
            )

        self.assertEqual(result, "Reporte listo")
        request = urlopen.call_args.args[0]
        self.assertIsInstance(request, Request)
        body = json.loads(request.data)
        self.assertEqual(body["model"], "qwen2.5:3b")
        self.assertFalse(body["stream"])
        self.assertEqual(body["options"], {"temperature": 0})
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertIn("exclusivamente en español", body["messages"][0]["content"])
        self.assertIn("## Resumen general", body["messages"][0]["content"])
        self.assertEqual(body["messages"][1]["role"], "user")
        self.assertIn(REPORT_PROMPT, body["messages"][1]["content"])
        self.assertIn("No uses inglés", body["messages"][1]["content"])
        self.assertIn("La respuesta DEBE comenzar exactamente", body["messages"][1]["content"])
        self.assertIn('"total_alerts": 2', body["messages"][1]["content"])

    @patch("infrastructure.alert_processing.ollama.urlopen")
    def test_rejects_empty_model_response(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        with patch("infrastructure.alert_processing.ollama.json.load", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "non-empty"):
                generate_report({}, base_url="http://ollama:11434", model="model")
