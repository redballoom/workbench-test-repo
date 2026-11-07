"""Test implementation of the yingdao callback -> Bitable update path."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from bitable_client import BitableClient

TASK_STATUS_MAP = {
    "created": "🟢 空闲",
    "waiting": "🟢 空闲",
    "running": "🔵 运行中",
    "finish": "🟢 空闲",
    "stopping": "🔵 运行中",
    "stopped": "🟢 空闲",
    "error": "🔴 故障/离线",
}


def parse_datetime_to_ms(value: Optional[str | int | float]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 0:
        return int(value * 1000) if value < 10**12 else int(value)
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return int(datetime.strptime(text, fmt).timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"unsupported datetime: {value}")


def update_task_record(client: BitableClient, task_uuid: str, status: str, start_time=None, end_time=None) -> dict:
    """Find one Task row by taskUUID and update it.

    Baseline behavior: one search + one update. A timeout in update is raised
    to the caller. The build stage adds retry/readback semantics.
    """
    records = client.search_records({
        "conjunction": "and",
        "conditions": [{"field_name": "taskUUID", "operator": "is", "value": [task_uuid]}],
    })
    if not records:
        return {"success": False, "outcome": "not_found", "updated": 0, "message": f"taskUUID={task_uuid} not found"}

    fields: dict[str, Any] = {"资产状态": TASK_STATUS_MAP.get(status, status)}
    if start_time is not None:
        fields["开始运行时间"] = parse_datetime_to_ms(start_time)
    if end_time is not None:
        fields["最后结束运行时间"] = parse_datetime_to_ms(end_time)

    updated = 0
    for record in records:
        client.update_record(record["record_id"], fields)
        updated += 1
    return {"success": True, "outcome": "written", "updated": updated, "message": f"updated {updated} rows"}


def process_yingdao_callback(client: BitableClient, callback_data: dict) -> dict:
    task = update_task_record(
        client,
        callback_data.get("taskUuid", ""),
        callback_data.get("status") or callback_data.get("taskStatus", ""),
        callback_data.get("startTime"),
        callback_data.get("endTime"),
    )
    jobs = []
    for job in callback_data.get("jobList", []):
        jobs.append({
            "robotName": job.get("robotName", ""),
            "success": True,
            "outcome": "written",
            "message": "test fixture: job update is represented by the task path",
        })
    return {"success": bool(task.get("success") and all(item["success"] for item in jobs)), "task": task, "jobs": jobs}
