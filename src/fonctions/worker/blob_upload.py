import logging
import json

import azure.functions as func

from cosmos_jobs import extract_job_id_from_blob_name, update_job
from signalr_messages import HUB_NAME, job_update_payload, serialize_signalr_messages

blob_upload_bp = func.Blueprint()


@blob_upload_bp.function_name(name="BlobUpload")
@blob_upload_bp.blob_trigger(
    arg_name="myblob",
    path="doc-storage/{name}",
    connection="dockstorage",
)
@blob_upload_bp.service_bus_queue_output(
    arg_name="queue_msg",
    queue_name="docq",
    connection="docbus",
)
@blob_upload_bp.generic_output_binding(
    arg_name="signalRMessages",
    type="signalR",
    hubName=HUB_NAME,
    connectionStringSetting="AzureSignalRConnectionString",
)
def blob_upload(
    myblob: func.InputStream,
    queue_msg: func.Out[str],
    signalRMessages: func.Out[str],
):
    logging.info(
        "Blob trigger processed blob. Name=%s Size=%s bytes",
        myblob.name,
        myblob.length,
    )

    job_id = extract_job_id_from_blob_name(myblob.name)
    if not job_id:
        logging.warning("Could not extract job_id from blob name=%s", myblob.name)
        return

    try:
        update_job(job_id, {"status": "UPLOADED"})
        logging.info("Job %s updated: status=UPLOADED", job_id)

        queue_msg.set(
            json.dumps(
                {
                    "id": job_id,
                    "blobName": myblob.name,
                    "size": myblob.length,
                }
            )
        )
        signalRMessages.set(
            serialize_signalr_messages(job_update_payload(job_id, "UPLOADED"))
        )
        logging.info("Job %s sent to Service Bus queue docq", job_id)
    except Exception:
        logging.exception("Cosmos update failed for job_id=%s", job_id)
