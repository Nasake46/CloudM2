import os
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import CosmosClient

_cosmos_client: CosmosClient | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_cosmos_container():
    global _cosmos_client

    if _cosmos_client is None:
        conn_str = os.getenv("COSMOS_CONNECTION_STRING")
        if conn_str:
            _cosmos_client = CosmosClient.from_connection_string(conn_str)
        else:
            endpoint = os.getenv("COSMOS_ENDPOINT")
            key = os.getenv("COSMOS_KEY")
            if not endpoint or not key:
                raise RuntimeError(
                    "Missing Cosmos configuration. Define COSMOS_CONNECTION_STRING "
                    "or COSMOS_ENDPOINT and COSMOS_KEY in Function App settings."
                )
            _cosmos_client = CosmosClient(endpoint, credential=key)

    database = os.getenv("COSMOS_DATABASE", "db-doc")
    container = os.getenv("COSMOS_CONTAINER", "jobs")
    return _cosmos_client.get_database_client(database).get_container_client(container)


def update_job(job_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    container = get_cosmos_container()
    item = container.read_item(item=job_id, partition_key="JOB")
    item.update(changes)
    item["updated_at"] = now_iso()
    container.replace_item(item=item["id"], body=item)
    return item


def extract_job_id_from_blob_name(blob_name: str) -> str | None:
    parts = [part for part in blob_name.split("/") if part]
    if not parts:
        return None
    if len(parts) >= 3:
        return parts[1]
    if len(parts) >= 2:
        return parts[0]
    return None
