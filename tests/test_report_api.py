import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from detection.http import ApiSettings, create_app
except ImportError as exc:  # fastapi or httpx not installed
    raise unittest.SkipTest(f"API test dependencies missing: {exc}")

SERVICE = "detection.http.report_service.generate_report"


class ReportApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.report_path = Path(self.tmp.name) / "report.json"
        settings = ApiSettings(
            report_path=self.report_path,
            ollama_url="http://ollama:11434",
            ollama_model="gemma3:4b",
            ollama_timeout=5.0,
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self):
        self.tmp.cleanup()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_missing_report_returns_404(self):
        response = self.client.post("/api/v1/reports", json={})
        self.assertEqual(response.status_code, 404)
        self.assertIn("does not exist", response.json()["detail"])

    def test_non_object_report_returns_404(self):
        self.report_path.write_text("[]", encoding="utf-8")
        response = self.client.post("/api/v1/reports")
        self.assertEqual(response.status_code, 404)
        self.assertIn("JSON object", response.json()["detail"])

    @patch(SERVICE, return_value="## Resumen\nok")
    def test_generates_report_with_default_model(self, generate):
        self.report_path.write_text('{"general": {}}', encoding="utf-8")
        response = self.client.post("/api/v1/reports")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"report": "## Resumen\nok"})
        generate.assert_called_once_with(
            {"general": {}},
            base_url="http://ollama:11434",
            model="gemma3:4b",
            timeout=5.0,
            print_stream=False,
        )

    @patch(SERVICE, return_value="texto")
    def test_request_model_overrides_default(self, generate):
        self.report_path.write_text("{}", encoding="utf-8")
        response = self.client.post("/api/v1/reports", json={"model": "llama3.2:3b"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate.call_args.kwargs["model"], "llama3.2:3b")

    @patch(SERVICE, side_effect=RuntimeError("Could not connect to Ollama"))
    def test_ollama_failure_returns_502(self, _generate):
        self.report_path.write_text("{}", encoding="utf-8")
        response = self.client.post("/api/v1/reports", json={})
        self.assertEqual(response.status_code, 502)

    def test_empty_model_is_rejected(self):
        response = self.client.post("/api/v1/reports", json={"model": ""})
        self.assertEqual(response.status_code, 422)


class ApiSettingsTests(unittest.TestCase):
    def test_summaries_dir_maps_to_sibling_report(self):
        settings = ApiSettings.from_env(summaries_dir="/data/summaries")
        self.assertEqual(settings.report_path, Path("/data/report.json"))

    @patch.dict("os.environ", {"REPORT_PATH": "/x/r.json", "OLLAMA_MODEL": "m",
                               "OLLAMA_BASE_URL": "http://o", "OLLAMA_TIMEOUT": "7"})
    def test_reads_environment(self):
        settings = ApiSettings.from_env()
        self.assertEqual(settings, ApiSettings(Path("/x/r.json"), "http://o", "m", 7.0))


if __name__ == "__main__":
    unittest.main()
