import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from callback_service import process_yingdao_callback


class FakeClient:
    def search_records(self, _filter):
        return [{"record_id": "rec-1"}]

    def write_with_readback(self, _record_id, _fields):
        return {"outcome": "not_written", "attempts": 3, "readback": True}


class CallbackSummaryTest(unittest.TestCase):
    def test_callback_does_not_report_success_for_not_written(self):
        result = process_yingdao_callback(FakeClient(), {
            "taskUuid": "task-1",
            "status": "running",
            "jobList": [],
        })
        self.assertFalse(result["success"])
        self.assertEqual(result["task"]["outcome"], "not_written")
        self.assertEqual(result["task"]["attempts"], 3)


if __name__ == "__main__":
    unittest.main()
