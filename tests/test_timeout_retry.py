import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bitable_client import BitableClient


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")
        return None

    def json(self):
        return self._data


class RetryContractTest(unittest.TestCase):
    def client(self):
        client = BitableClient(
            "test-app", "test-secret", "test-token", "test-table",
            timeout=1, max_attempts=3, backoff_base=0, backoff_max=0,
            sleep=lambda _: None,
        )
        client._access_token = "test-access-token"
        client._token_expire_time = 9999999999
        return client

    def test_update_retries_after_timeout(self):
        response = FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-1"}}})
        with patch("bitable_client.requests.request", side_effect=[requests.Timeout("read timeout"), response]) as request:
            result = self.client().update_record("rec-1", {"资产状态": "🔵 运行中"})
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result["record_id"], "rec-1")

    def test_create_reuses_client_token(self):
        response = FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-2"}}})
        with patch("bitable_client.requests.request", side_effect=[requests.Timeout("timeout"), response]) as request:
            result = self.client().create_record({"taskUUID": "task-1"}, client_token="fixed-token")
        self.assertEqual(result["record_id"], "rec-2")
        tokens = [call.kwargs.get("params", {}).get("client_token") for call in request.call_args_list]
        self.assertEqual(tokens, ["fixed-token", "fixed-token"])

    def test_write_with_readback_marks_written_after_exhausted_timeouts(self):
        record = FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-3", "fields": {"资产状态": "🔵 运行中"}}}})
        with patch("bitable_client.requests.request", side_effect=[
            requests.Timeout("t1"), requests.Timeout("t2"), requests.Timeout("t3"), record,
        ]):
            result = self.client().write_with_readback("rec-3", {"资产状态": "🔵 运行中"})
        self.assertEqual(result["outcome"], "written")
        self.assertTrue(result["readback"])
        self.assertEqual(result["attempts"], 3)

    def test_write_with_readback_marks_not_written_when_readback_differs(self):
        record = FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-4", "fields": {"资产状态": "🟢 空闲"}}}})
        with patch("bitable_client.requests.request", side_effect=[
            requests.Timeout("t1"), requests.Timeout("t2"), requests.Timeout("t3"), record,
        ]):
            result = self.client().write_with_readback("rec-4", {"资产状态": "🔵 运行中"})
        self.assertEqual(result["outcome"], "not_written")
        self.assertTrue(result["readback"])

    def test_write_with_readback_marks_unknown_when_readback_times_out(self):
        with patch("bitable_client.requests.request", side_effect=[
            requests.Timeout("t1"), requests.Timeout("t2"), requests.Timeout("t3"), requests.Timeout("readback"),
        ]):
            result = self.client().write_with_readback("rec-5", {"资产状态": "🔵 运行中"})
        self.assertEqual(result["outcome"], "unknown")
        self.assertIn("readback failed", result["error"])

    def test_400_is_not_retried(self):
        response = FakeResponse({"code": 400, "msg": "bad request"}, status=400)
        with patch("bitable_client.requests.request", side_effect=[response]) as request:
            with self.assertRaises(requests.HTTPError):
                self.client().update_record("rec-6", {"资产状态": "x"})
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
