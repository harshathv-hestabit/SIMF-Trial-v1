from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parents[4] / ".env"

if not _ENV_PATH.exists():
    raise FileNotFoundError(
        f"[Settings] .env file not found at {_ENV_PATH}\n"
        f"  - In Docker: ensure the bind mount './.env:/app/.env:ro' is set in docker-compose.yaml\n"
        f"  - Locally: ensure .env exists at the project root"
    )

class Settings(BaseSettings):
    GROQ_BASE_URL: str = Field(..., description="Groq API base URL")
    GROQ_API_KEY: str = Field(..., description="Groq API key")

    COSMOS_URL: str = Field(..., description="Cosmos DB endpoint")
    COSMOS_KEY: str = Field(..., description="Cosmos DB key")
    COSMOS_DB: str = Field(..., description="Cosmos DB name")
    NEWS_CONTAINER: str = Field(..., description="News Container Name")
    CLIENT_PORTFOLIO_CONTAINER: str = Field(..., description="Client Portfolio Container Name")
    INSIGHTS_CONTAINER: str = Field(..., description="Insights Container Name")
    NEWS_CONTAINER_PARTITION_ID: str = Field(..., description="News Container Partition ID")
    CLIENT_PORTFOLIO_CONTAINER_PARTITION_ID: str = Field(..., description="Client Portfolio Container Partition ID")
    INSIGHTS_CONTAINER_PARTITION_ID: str = Field(..., description="Insights Container Partition ID")

    EVENTHUB_NAME: str = Field(..., description="Event Hub name")
    EVENTHUB_CONNECTION_STRING: str = Field(..., description="Event Hub Connection String")
    CHECKPOINT_CONTAINER:str = Field(...,description="Eventhub checkpoint container")
    AZURE_STORAGE_ACCOUNT: str = Field(..., description="Storage account name")
    AZURE_STORAGE_KEY: str = Field(..., description="Storage account key")
    AZURE_STORAGE_CONNECTION_STRING: str = Field(..., description="Storage connection string")

    EODHD_API_KEY: str = Field(..., description="EODHD API key")
    HF_TOKEN: str = Field(..., description="HuggingFace token")

    GOOGLE_API_KEY: str = Field(...,description="Gemini API Key")
    
    ELASTICSEARCH_URL: str = Field(...,description="Elastic Search Endpoint")
    
    model_config = SettingsConfigDict(
        env_file=_ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()