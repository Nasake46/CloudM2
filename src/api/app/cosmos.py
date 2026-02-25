from azure.cosmos import CosmosClient
from .config import settings

_client: CosmosClient | None = None

def get_cosmos_container():
    global _client
    if _client is None:
        _client = CosmosClient(settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY)
    
    db = _client.get_database_client(settings.COSMOS_DATABASE)
    container = db.get_container_client(settings.COSMOS_CONTAINER)
    return container