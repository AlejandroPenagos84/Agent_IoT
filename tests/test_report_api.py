import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
    from detection.http import ApiSettings, build_container, create_app
except ImportError as exc:  # fastapi, httpx or pyjwt not installed
    raise unittest.SkipTest(f"API test dependencies missing: {exc}")

SERVICE = "detection.http.report_service.generate_report"
SECRET = "test-secret"
NOW = "2026-11-08T12:00:00Z"
NOW_TS = 1_794_139_200.0  # 2026-11-08T12:00:00Z


def _auth(user_id):
    token = PyJwtTokenService(SECRET, 15, 10080).create_access(user_id)
    return {"Authorization": f"Bearer {token}"}


class ReportApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.container = build_container(
            db_path=str(root / "detection.db"), jwt_secret=SECRET,
            alerts_dir=root / "alerts", sensor_ttl_minutes=60)
        settings = ApiSettings(
            report_path=root / "report.json",
            ollama_url="http://ollama:11434",
            ollama_model="gemma3:4b",
            ollama_timeout=5.0,
            report_timezone="UTC",
        )
        self.client = TestClient(create_app(settings, container=self.container))
        self.client.__enter__()
        self.headers = _auth("user-1")
        store = self.container.store
        self.broker_a = store.create_broker("user-1", "bodega", None, None)["id"]
        self.broker_b = store.create_broker("user-1", "oficina", None, None)["id"]
        other = store.create_broker("user-2", "ajeno", None, None)["id"]
        self.other_broker = other
        for index in range(3):
            self._alert(f"a-{index}", "user-1", self.broker_a,
                        NOW_TS - 600 + index, "10.0.0.1")
        self._alert("b-0", "user-1", self.broker_b, NOW_TS - 300, "10.0.0.2")
        self._alert("x-0", "user-2", other, NOW_TS - 100, "10.9.9.9")
        self._alert("x-1", "user-2", other, NOW_TS - 90, "10.9.9.9")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def _alert(self, alert_id, tenant, broker, ts, ip):
        self.container.store.add_alert({
            "alert_id": alert_id, "tenant_id": tenant, "broker_id": broker,
            "sensor_id": None, "ts": ts, "kind": "class", "label": "ataque",
            "client_id": "c1", "ip": ip, "topic": "home/t", "source": "tshark-tcp",
        })

    def _analytics(self, headers=None, **params):
        return self.client.get("/api/v1/reports/analytics",
                               params={"now": NOW, **params},
                               headers=headers or self.headers)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_reports_require_authentication(self):
        self.assertEqual(self.client.post("/api/v1/reports", json={}).status_code, 401)
        self.assertEqual(
            self.client.get("/api/v1/reports/analytics").status_code, 401)

    def test_tenant_report_only_counts_own_alerts(self):
        response = self._analytics()
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report["general"]["total_alerts"], 4)
        self.assertEqual(report["scope"]["tenant_id"], "user-1")
        self.assertIsNone(report["scope"]["broker_id"])
        ips = {item["ip"] for item in report["ips"]["top_10"]}
        self.assertEqual(ips, {"10.0.0.1", "10.0.0.2"})
        brokers = {item["broker_name"]: item["alert_count"]
                   for item in report["brokers"]}
        self.assertEqual(brokers, {"bodega": 3, "oficina": 1})

        other = self._analytics(headers=_auth("user-2")).json()
        self.assertEqual(other["general"]["total_alerts"], 2)
        self.assertEqual([item["ip"] for item in other["ips"]["top_10"]],
                         ["10.9.9.9"])

    def test_broker_report_is_filtered(self):
        response = self._analytics(broker_id=self.broker_b)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report["general"]["total_alerts"], 1)
        self.assertEqual(report["scope"]["broker_name"], "oficina")
        self.assertEqual([item["broker_id"] for item in report["brokers"]],
                         [self.broker_b])

    def test_other_tenant_broker_returns_404(self):
        response = self._analytics(broker_id=self.other_broker)
        self.assertEqual(response.status_code, 404)

    def test_tenant_without_alerts_returns_404(self):
        response = self._analytics(headers=_auth("user-3"))
        self.assertEqual(response.status_code, 404)

    def test_historical_fallback_uses_latest_alerts(self):
        response = self._analytics(now="2026-11-20T00:00:00Z")
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertTrue(report["period"]["historical_fallback"])
        self.assertEqual(report["general"]["total_alerts"], 4)

    def test_invalid_now_returns_400(self):
        self.assertEqual(self._analytics(now="ayer").status_code, 400)
        response = self.client.post("/api/v1/reports", json={"now": "ayer"},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 400)

    @patch(SERVICE, return_value="## Resumen\nok")
    def test_natural_report_uses_scoped_data(self, generate):
        response = self.client.post(
            "/api/v1/reports", json={"now": NOW, "broker_id": self.broker_a},
            headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"report": "## Resumen\nok"})
        payload = generate.call_args.args[0]
        self.assertEqual(payload["general"]["total_alerts"], 3)
        self.assertNotIn("tenant_id", payload["scope"])
        self.assertEqual(generate.call_args.kwargs["model"], "gemma3:4b")

    @patch(SERVICE, return_value="texto")
    def test_request_model_overrides_default(self, generate):
        response = self.client.post(
            "/api/v1/reports", json={"now": NOW, "model": "llama3.2:3b"},
            headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate.call_args.kwargs["model"], "llama3.2:3b")

    @patch(SERVICE, side_effect=RuntimeError("Could not connect to Ollama"))
    def test_ollama_failure_returns_502(self, _generate):
        response = self.client.post("/api/v1/reports", json={"now": NOW},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 502)

    def test_empty_model_is_rejected(self):
        response = self.client.post("/api/v1/reports", json={"model": ""},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 422)


class ApiSettingsTests(unittest.TestCase):
    def test_summaries_dir_maps_to_sibling_report(self):
        settings = ApiSettings.from_env(summaries_dir="/data/summaries")
        self.assertEqual(settings.report_path, Path("/data/report.json"))

    @patch.dict("os.environ", {"REPORT_PATH": "/x/r.json", "OLLAMA_MODEL": "m",
                               "OLLAMA_BASE_URL": "http://o", "OLLAMA_TIMEOUT": "7",
                               "REPORT_TIMEZONE": "UTC"})
    def test_reads_environment(self):
        settings = ApiSettings.from_env()
        self.assertEqual(settings, ApiSettings(Path("/x/r.json"), "http://o", "m",
                                               7.0, "UTC"))


if __name__ == "__main__":
    unittest.main()
