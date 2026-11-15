"""Cliente JSON sobre HTTP(S) de la API de sensores (solo biblioteca estándar)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from capture.application.errors import EnrollmentError
from capture.application.ports.enrollment_api import EnrollmentApi

ENROLL_PATH = '/api/v1/sensors/enroll'
REFRESH_PATH = '/api/v1/sensors/token/refresh'
HTTP_TIMEOUT = 15.0
REJECTED_STATUS = (401, 403, 404)


class ApiClient(EnrollmentApi):
    def __init__(self, base_url: str, ca_file: str | None = None, timeout: float = HTTP_TIMEOUT):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.context = None
        if self.base_url.startswith('https://'):
            self.context = ssl.create_default_context(cafile=ca_file)

    def enroll(self, enrollment_key: str, name: str) -> dict:
        return self.post(ENROLL_PATH, {'enrollment_key': enrollment_key, 'name': name})

    def refresh(self, sensor_secret: str) -> dict:
        return self.post(REFRESH_PATH, token=sensor_secret)

    def post(self, path: str, body: dict | None = None, token: str | None = None) -> dict:
        """Devuelve el JSON de respuesta; lanza ``EnrollmentError`` con 401/403/404."""
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        request = urllib.request.Request(
            self.base_url + path,
            method='POST',
            headers=headers,
            data=json.dumps(body or {}).encode('utf-8'),
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self.context
            ) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code in REJECTED_STATUS:
                detail = exc.read().decode('utf-8', errors='replace')[:200]
                raise EnrollmentError(f'HTTP {exc.code}: {detail}') from exc
            raise
