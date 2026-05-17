from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    COSMOS_ENDPOINT: str
    COSMOS_KEY: str
    COSMOS_DATABASE: str = "db-doc"
    COSMOS_CONTAINER: str = "jobs"
    BLOB_CONNECTION_STRING: str
    BLOB_CONTAINER: str
    FUNCTIONS_BASE_URL: str = (
        "https://nasa-function-app-h3dwcuhfhwaha2da.francecentral-01.azurewebsites.net"
    )

settings = Settings()