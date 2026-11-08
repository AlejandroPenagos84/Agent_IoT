import json
import unittest
from unittest.mock import patch
from urllib.request import Request

from detection.reporting.ollama import (
    REPORT_PROMPT,
    generate_report,
)


class OllamaReportTests(unittest.TestCase):
    @patch("detection.reporting.ollama.urlopen")
    def test_sends_json_and_prompt_to_chat_endpoint(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        ollama_report = "Based on the provided data, activity was observed."
        response.__iter__.return_value = iter((
            b'{"message":{"content":"Based on the "}}\n',
            b'{"message":{"content":"provided data, activity was observed."}}\n',
            b'{"done":true}\n',
        ))
        with patch("builtins.print"):
            result = generate_report(
                {"general": {"total_alerts": 2}},
                base_url="http://ollama:11434",
                model="gemma3:4b",
            )

        self.assertEqual(result, ollama_report)
        request = urlopen.call_args.args[0]
        self.assertIsInstance(request, Request)
        body = json.loads(request.data)
        self.assertEqual(body["model"], "gemma3:4b")
        self.assertTrue(body["stream"])
        self.assertEqual(body["options"], {"temperature": 0.2, "num_predict": 1200})
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertIn("exclusivamente en español", body["messages"][0]["content"])
        self.assertEqual(body["messages"][1]["role"], "user")
        self.assertIn(REPORT_PROMPT, body["messages"][1]["content"])
        self.assertIn("exclusivamente en español", body["messages"][1]["content"])
        self.assertIn('"total_alerts": 2', body["messages"][1]["content"])

    @patch("detection.reporting.ollama.urlopen")
    def test_rejects_empty_model_response(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.__iter__.return_value = iter((b'{"done":true}\n',))
        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "non-empty"):
                generate_report({}, base_url="http://ollama:11434", model="model")

    @patch("detection.reporting.ollama.urlopen")
    def test_rejects_json_instead_of_natural_report(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.__iter__.return_value = iter((
            b'{"message":{"content":"```json\\n{\\"alerts\\": []}\\n```"}}\n',
        ))
        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "input data"):
                generate_report({}, base_url="http://ollama:11434", model="model")
