from pydantic import AliasChoices, Field
from app.common.azure_services.settings import AzureServiceEmulatorSettings


class Settings(AzureServiceEmulatorSettings):
    LLM_BASE_URL: str = Field(
        ...,
        description="OpenAI-compatible LLM API base URL",
        validation_alias=AliasChoices("LLM_BASE_URL", "GROQ_BASE_URL"),
    )
    LLM_API_KEY: str = Field(
        ...,
        description="OpenAI-compatible LLM API key",
        validation_alias=AliasChoices("LLM_API_KEY", "GROQ_API_KEY"),
    )
    LLM_POOL_CONFIG: str = Field(
        default="",
        description="JSON array describing the LLM backend pool",
    )
    LLM_MAX_RETRIES: int = Field(3, description="Retries after pool exhaustion")
    LLM_TEMPERATURE: float = Field(0.3, description="Default LLM temperature")
    REALTIME_WORKFLOW_CONCURRENCY: int = Field(1, description="Concurrent realtime workflow executions")
    STANDARD_WORKFLOW_CONCURRENCY: int = Field(1, description="Concurrent standard workflow executions")
    STANDARD_WORKFLOW_BATCH_LIMIT: int = Field(50, description="Maximum delayed news items processed per standard workflow run")
    GENERATE_INSIGHT_CONCURRENCY: int = Field(1, description="Concurrent generate insight executions")
    SERVICEBUS_MAX_LOCK_RENEWAL_SECONDS: int = Field(
        900,
        description="Maximum lock renewal duration for long-running message handlers",
    )
    INSIGHT_JOB_PROCESSING_STALE_AFTER_SECONDS: int = Field(
        1800,
        description="Treat processing job state as stale after this many seconds",
    )

    GOOGLE_API_KEY: str = Field(..., description="Gemini API Key")
    ELASTICSEARCH_URL: str = Field(..., description="Elastic Search Endpoint")

settings = Settings()
