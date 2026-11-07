"""Minimal Feishu Bitable client used by the workbench test fixture.

This file intentionally models the production callback SDK's write path:
- one HTTP request per operation;
- no retry/backoff;
- no readback after timeout.

The build stage will add the retry/idempotency behavior described in
docs/design.md. Tests in tests/test_timeout_retry.py define the expected
behavior and are expected to fail before that change.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

import requests


class BitableError(Exception):
    """A non-success response from the Bitable API."""


class BitableClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        base_url: str = "https://open.feishu.cn/open-apis",
        timeout: float = 20,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.base_url = base_url
        self.timeout = timeout
        self._access_token: Optional[str] = None
        self._token_expire_time = 0.0

    def get_access_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._access_token and self._token_expire_time > 0:
            return self._access_token
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        resp = requests.post(url, json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=self.timeout)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 0:
            raise BitableError(f"token failed: {result.get('msg')}")
        self._access_token = result["tenant_access_token"]
        self._token_expire_time = float(result.get("expire", 7200))
        return self._access_token

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        token = self.get_access_token()
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 0:
            raise BitableError(f"API failed: {result.get('msg')}")
        return result.get("data", {})

    def search_records(self, filter_spec: dict) -> list:
        path = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/search"
        return self._request("POST", path, json={"filter": filter_spec, "automatic_fields": False}).get("items", [])

    def get_record(self, record_id: str) -> dict:
        path = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
        return self._request("GET", path).get("record", {})

    def update_record(self, record_id: str, fields: dict) -> dict:
        path = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
        return self._request("PUT", path, json={"fields": fields}).get("record", {})

    def create_record(self, fields: dict, client_token: Optional[str] = None) -> dict:
        path = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        params = {}
        if client_token:
            params["client_token"] = client_token
        return self._request("POST", path, params=params, json={"fields": fields}).get("record", {})
