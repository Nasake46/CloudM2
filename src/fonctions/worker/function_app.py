import azure.functions as func
import logging
import os
from datetime import datetime, timezone
from azure.cosmos import CosmosClient

app = func.FunctionApp()

_cosmos_client: CosmosClient | None = None

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _get_cosmos_container():
    global _cosmos_client
    if _cosmos_client is None:
        endpoint = os.environ["COSMOS_ENDPOINT"]
        key = os.environ["COSMOS_KEY"]
        _cosmos_client = CosmosClient(endpoint, credential=key)

    db_name = os.getenv("COSMOS_DATABASE", "db-doc")
    container_name = os.getenv("COSMOS_CONTAINER", "jobs")
    db = _cosmos_client.get_database_client(db_name)
    return db.get_container_client(container_name)

def _extract_job_id(blob_name: str) -> str | None:
    # `myblob.name` peut être "container/job_id/file.ext" ou "job_id/file.ext"
    parts = [p for p in blob_name.split("/") if p]
    if not parts:
        return None
    if len(parts) >= 3:
        return parts[1]
    if len(parts) >= 2:
        return parts[0]
    return None

@app.function_name(name="BlobUpload")
@app.blob_trigger(arg_name="myblob", path="doc-storage/{name}",
                               connection="dockstorage") 
def blob_upload(myblob: func.InputStream):
    logging.info(
        "Python blob trigger processed blob. Name=%s Size=%s bytes",
        myblob.name,
        myblob.length,
    )

    job_id = _extract_job_id(myblob.name)
    if not job_id:
        logging.warning("Impossible d'extraire un job_id depuis le blob name=%s", myblob.name)
        return

    try:
        container = _get_cosmos_container()
        item = container.read_item(item=job_id, partition_key="JOB")
        item["status"] = "UPLOADED"
        item["updated_at"] = _now_iso()
        container.replace_item(item=item["id"], body=item)
        logging.info("Job %s mis à jour: status=UPLOADED", job_id)
    except Exception as e:
        logging.exception("Échec update Cosmos pour job_id=%s: %s", job_id, str(e))
