"""Run three mock syncs and emit machine-readable run evidence.

This is a fixture runner, not a production executor. It uses a fake client and
never contacts Feishu or any external system.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from callback_service import process_yingdao_callback


class WrittenClient:
    def search_records(self, _filter):
        return [{"record_id": "rec-1"}]

    def write_with_readback(self, _record_id, _fields):
        return {"outcome": "written", "attempts": 1, "readback": True}


def main() -> int:
    runs = []
    for index in range(1, 4):
        result = process_yingdao_callback(WrittenClient(), {
            "taskUuid": f"fixture-task-{index}",
            "status": "finish",
            "startTime": "2026-11-07 12:00:00",
            "endTime": "2026-11-07 12:00:20",
            "jobList": [],
        })
        runs.append({
            "runId": f"FIXTURE-RUN-{index:03d}",
            "taskUuid": f"fixture-task-{index}",
            "status": "succeeded" if result["success"] else "failed",
            "outcome": result["task"].get("outcome"),
            "attempts": result["task"].get("attempts"),
        })
    payload = {
        "status": "succeeded" if all(run["status"] == "succeeded" for run in runs) else "failed",
        "environment": "fixture",
        "executedAt": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        "artifacts": [
            {"path": "bitable_client.py", "kind": "implementation"},
            {"path": "callback_service.py", "kind": "implementation"},
            {"path": "tests/test_three_runs.py", "kind": "test"},
        ],
        "verification": {"kind": "mock", "production": False, "acceptance": "AC-03"},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
