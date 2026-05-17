import os

from azure.storage.blob import BlobServiceClient

_blob_service: BlobServiceClient | None = None


def get_blob_service() -> BlobServiceClient:
    global _blob_service
    if _blob_service is None:
        connection_string = os.getenv("dockstorage")
        if not connection_string:
            raise RuntimeError("Missing dockstorage connection string in Function App settings.")
        _blob_service = BlobServiceClient.from_connection_string(connection_string)
    return _blob_service


def blob_exists(blob_name: str) -> bool:
    container_name = os.getenv("BLOB_CONTAINER", "doc-storage")
    blob_client = get_blob_service().get_blob_client(
        container=container_name,
        blob=blob_name,
    )
    return blob_client.exists()
