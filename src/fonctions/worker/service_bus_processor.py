import json
import logging

import azure.functions as func

from cosmos_jobs import now_iso, update_job

service_bus_bp = func.Blueprint()


@service_bus_bp.function_name(name="ProcessDocument")
@service_bus_bp.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="docq",
    connection="docbus",
)
def process_document(msg: func.ServiceBusMessage):
    raw_body = msg.get_body().decode("utf-8")
    logging.info("Service Bus message received: %s", raw_body)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logging.exception("Service Bus message is not valid JSON")
        raise

    job_id = payload.get("id") or payload.get("jobId")
    if not job_id:
        raise ValueError("Service Bus message must contain an 'id' or 'jobId' field")

    try:
        update_job(job_id, {"status": "PROCESSING"})
        logging.info("Job %s updated: status=PROCESSING", job_id)

        tags = payload.get("tags") or ["azure", "cloud", "document"]

        update_job(
            job_id,
            {
                "status": "PROCESSED",
                "tags": tags,
                "processedAt": now_iso(),
            },
        )
        logging.info("Job %s updated: status=PROCESSED tags=%s", job_id, tags)
    except Exception:
        logging.exception("Service Bus processing failed for job_id=%s", job_id)
        raise
