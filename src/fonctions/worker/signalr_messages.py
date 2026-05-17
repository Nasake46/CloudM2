import json
from typing import Any

HUB_TARGET = "jobUpdated"
HUB_NAME = "jobs"


def job_update_payload(
    job_id: str,
    status: str,
    *,
    tags: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"jobId": job_id, "status": status}
    if tags is not None:
        payload["tags"] = tags
    if error is not None:
        payload["error"] = error
    return payload


def serialize_signalr_messages(*payloads: dict[str, Any]) -> str:
    messages = [{"target": HUB_TARGET, "arguments": [payload]} for payload in payloads]
    if len(messages) == 1:
        return json.dumps(messages[0])
    return json.dumps(messages)
