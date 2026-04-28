import azure.functions as func
import logging
import os
from datetime import datetime, timezone

from azure.cosmos import CosmosClient

app = func.FunctionApp()


@app.blob_trigger(arg_name="myblob", path="doc-storage/{name}",
                               connection="docstorage") 
def Test(myblob: func.InputStream):
    blob_full_name = myblob.name or ""
    blob_name = os.path.basename(blob_full_name.replace("\\", "/"))

    logging.info("Blob reçu: %s (%s bytes)", blob_full_name, myblob.length)

    endpoint = os.environ["COSMOS_ENDPOINT"]
    key = os.environ["COSMOS_KEY"]
    database = os.getenv("COSMOS_DATABASE", "db-doc")
    container_name = os.getenv("COSMOS_CONTAINER", "jobs")

    client = CosmosClient(endpoint, credential=key)
    container = client.get_database_client(database).get_container_client(container_name)

    items = list(
        container.query_items(
            query="SELECT * FROM c WHERE c.pk='JOB' AND c.fileName=@fileName",
            parameters=[{"name": "@fileName", "value": blob_name}],
            enable_cross_partition_query=True,
        )
    )
    if not items:
        logging.warning("Aucun job Cosmos trouvé pour fileName=%s", blob_name)
        return

    job = items[0]
    job["status"] = "UPLOADED"
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    container.replace_item(item=job["id"], body=job, partition_key=job.get("pk", "JOB"))