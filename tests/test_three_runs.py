import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from callback_service import process_yingdao_callback


class WrittenClient:
    def search_records(self, _filter):
        return [{"record_id": "rec-1"}]

    def write_with_readback(self, _record_id, _fields):
        return {"outcome": "written", "attempts": 1, "readback": True}


class ThreeConsecutiveRunsTest(unittest.TestCase):
    def test_three_consecutive_mock_runs_succeed(self):
        results = [
            process_yingdao_callback(WrittenClient(), {
                "taskUuid": f"task-{index}",
                "status": "finish",
                "startTime": "2026-11-07 12:00:00",
                "endTime": "2026-11-07 12:00:20",
                "jobList": [],
            })
            for index in range(1, 4)
        ]
        self.assertEqual(len(results), 3)
        self.assertTrue(all(result["success"] for result in results))
        self.assertTrue(all(result["task"]["outcome"] == "written" for result in results))


if __name__ == "__main__":
    unittest.main()
