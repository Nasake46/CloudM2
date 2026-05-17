import json
import logging

import azure.functions as func

from cosmos_jobs import update_job
from service_bus_security import sanitize_error_text
from signalr_messages import HUB_NAME, job_update_payload, serialize_signalr_messages

dlq_bp = func.Blueprint()


def extract_job_id(payload: dict | None) -> str | None:
    if not payload:
        return None
    job_id = payload.get("id") or payload.get("jobId")
    if isinstance(job_id, str) and job_id.strip():
        return job_id.strip()
    return None


def parse_payload(raw_body: str) -> dict | None:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def dead_letter_metadata(msg: func.ServiceBusMessage) -> tuple[str | None, str | None]:
    reason = getattr(msg, "dead_letter_reason", None)
    description = getattr(msg, "dead_letter_error_description", None)
    if reason or description:
        return reason, description

    properties = msg.application_properties or {}
    reason = properties.get("DeadLetterReason") or properties.get(b"DeadLetterReason")
    description = properties.get("DeadLetterErrorDescription") or properties.get(
        b"DeadLetterErrorDescription"
    )
    if isinstance(reason, bytes):
        reason = reason.decode("utf-8", errors="replace")
    if isinstance(description, bytes):
        description = description.decode("utf-8", errors="replace")
    return reason, description


def publish_failed_status(
    job_id: str,
    error_message: str,
    signalRMessages: func.Out[str],
) -> None:
    update_job(
        job_id,
        {
            "status": "FAILED",
            "error": error_message,
            "deadLetter": True,
        },
    )
    signalRMessages.set(
        serialize_signalr_messages(
            job_update_payload(job_id, "FAILED", error=error_message)
        )
    )


@dlq_bp.function_name(name="ProcessDeadLetter")
@dlq_bp.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="docq/$DeadLetterQueue",
    connection="docbus",
)
@dlq_bp.generic_output_binding(
    arg_name="signalRMessages",
    type="signalR",
    hubName=HUB_NAME,
    connectionStringSetting="AzureSignalRConnectionString",
)
def process_dead_letter(msg: func.ServiceBusMessage, signalRMessages: func.Out[str]):
    raw_body = msg.get_body().decode("utf-8")
    dlq_reason, dlq_description = dead_letter_metadata(msg)
    delivery_count = getattr(msg, "delivery_count", None)

    logging.error(
        "DLQ message received delivery_count=%s reason=%s description=%s body=%s",
        delivery_count,
        dlq_reason,
        dlq_description,
        raw_body,
    )

    payload = parse_payload(raw_body)
    job_id = extract_job_id(payload)

    if not job_id:
        logging.error(
            "DLQ message without job id (malformed payload). reason=%s body=%s",
            dlq_reason,
            raw_body,
        )
        return

    error_message = sanitize_error_text(
        dlq_description
        or dlq_reason
        or "Le document n'a pas pu être traité après plusieurs tentatives."
    )

    try:
        publish_failed_status(job_id, error_message, signalRMessages)
        logging.info("Job %s marked FAILED from DLQ handler", job_id)
    except Exception:
        logging.exception("DLQ handler failed for job_id=%s", job_id)
        raise
