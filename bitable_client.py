"""Minimal Feishu Bitable client used by the workbench test fixture.

This file models the production callback SDK's write path and adds:
- bounded retry/backoff for timeout, 429 and 5xx;
- idempotent create tokens reused across retries;
- readback after a write timeout.

All tests use mock HTTP; no real Feishu endpoint is called.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

import requests


class BitableError(Exception):
    """A non-success response from the Bitable API."""


class BitableTimeoutError(BitableError):
    """All retry attempts timed out or the readback could not be completed."""

    def __init__(self, message: str, *, attempts: int = 0, outcome: str = "unknown") -> None:
        super().__init__(message)
        self.attempts = attempts
        self.outcome = outcome


class BitableClient:
    RETRY_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        base_url: str = "https://open.feishu.cn/open-apis",
        timeout: float = 20,
        max_attempts: int = 3,
        backoff_base: float = 0.2,
        backoff_max: float = 2.0,
        sleep=time.sleep,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.base_url = base_url
        self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_base = max(0.0, float(backoff_base))
        self.backoff_max = max(self.backoff_base, float(backoff_max))
        self._sleep = sleep
        self.last_attempts = 0
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

    def _retry_delay(self, attempt: int, response=None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After") if getattr(response, "headers", None) else None
            if retry_after:
                try:
                    return min(self.backoff_max, max(0.0, float(retry_after)))
                except ValueError:
                    pass
        return min(self.backoff_max, self.backoff_base * (2 ** max(0, attempt - 1)))

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        token = self.get_access_token()
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        last_timeout: Optional[BaseException] = None
        self.last_attempts = 0

        for attempt in range(1, self.max_attempts + 1):
            self.last_attempts = attempt
            try:
                resp = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
            except (requests.Timeout, requests.ConnectionError) as error:
                last_timeout = error
                if attempt >= self.max_attempts:
                    raise BitableTimeoutError(
                        f"request timed out after {attempt} attempt(s): {error}",
                        attempts=attempt,
                        outcome="unknown",
                    ) from error
                self._sleep(self._retry_delay(attempt))
                continue

            if resp.status_code in self.RETRY_STATUS:
                if attempt >= self.max_attempts:
                    raise BitableError(f"API retry exhausted: HTTP {resp.status_code}")
                self._sleep(self._retry_delay(attempt, resp))
                continue

            resp.raise_for_status()
            result = resp.json()
            if result.get("code") != 0:
                raise BitableError(f"API failed: {result.get('msg')}")
            return result.get("data", {})

        raise BitableTimeoutError("request did not complete", attempts=self.max_attempts, outcome="unknown") from last_timeout

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
        # Reuse one token across all retry attempts for this logical create.
        token = client_token or str(uuid.uuid4())
        return self._request("POST", path, params={"client_token": token}, json={"fields": fields}).get("record", {})

    def write_with_readback(self, record_id: str, fields: dict) -> dict:
        """Update one record; after a timeout, read back and classify the outcome."""
        attempts = 0
        try:
            record = self.update_record(record_id, fields)
            attempts = self.last_attempts
            return {"outcome": "written", "attempts": attempts, "record": record, "readback": False}
        except BitableTimeoutError as error:
            attempts = error.attempts
            error_outcome = error.outcome
        except BitableError:
            raise

        try:
            current = self.get_record(record_id)
        except Exception as error:
            return {
                "outcome": "unknown",
                "attempts": attempts,
                "error": f"write timeout; readback failed: {error}",
                "readbackError": str(error),
            }

        actual = current.get("fields", {})
        matched = all(actual.get(key) == value for key, value in fields.items())
        return {
            "outcome": "written" if matched else "not_written",
            "attempts": attempts,
            "record": current,
            "readback": True,
            "previousError": error_outcome,
        }
