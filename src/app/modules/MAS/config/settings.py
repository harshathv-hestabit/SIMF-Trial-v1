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
    LLM_POOL_CONFIG: str = Field(
        default="",
        description="JSON array describing the LLM backend pool",
    )
    LLM_MAX_RETRIES: int = Field(3, description="Retries after pool exhaustion")
    LLM_TEMPERATURE: float = Field(0.3, description="Default LLM temperature")

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
    SERVICEBUS_CONNECTION_STRING: str = Field(..., description="Azure Service Bus connection string")
    QUEUE_REALTIME_NEWS: str = Field("realtime-news-events", description="Realtime workflow queue")
    QUEUE_STANDARD_NEWS: str = Field("standard-news-events", description="Standard workflow queue")
    QUEUE_GENERATE_INSIGHT: str = Field("generate-insight-events", description="Generate insight queue")
    REALTIME_WORKFLOW_CONCURRENCY: int = Field(1, description="Concurrent realtime workflow executions")
    STANDARD_WORKFLOW_CONCURRENCY: int = Field(1, description="Concurrent standard workflow executions")
    GENERATE_INSIGHT_CONCURRENCY: int = Field(1, description="Concurrent generate insight executions")
    SERVICEBUS_MAX_DELIVERY_ATTEMPTS: int = Field(5, description="Dead-letter after this many delivery attempts")

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
