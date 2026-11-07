import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bitable_client import BitableClient


class FakeResponse:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class RetryContractTest(unittest.TestCase):
    def client(self):
        client = BitableClient("test-app", "test-secret", "test-token", "test-table")
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
        first = FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-2"}}})
        with patch("bitable_client.requests.request", side_effect=[requests.Timeout("timeout"), first]) as request:
            result = self.client().create_record({"taskUUID": "task-1"}, client_token="fixed-token")
        self.assertEqual(result["record_id"], "rec-2")
        tokens = [call.kwargs.get("params", {}).get("client_token") for call in request.call_args_list]
        self.assertEqual(tokens, ["fixed-token", "fixed-token"])


if __name__ == "__main__":
    unittest.main()
