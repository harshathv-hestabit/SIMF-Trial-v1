from pydantic import Field

from app.common.azure_services.settings import AzureServiceEmulatorSettings


class Settings(AzureServiceEmulatorSettings):
    UI_API_PORT: int = Field(8088, description="Port for the UI API service")
    UI_CORS_ORIGINS: str = Field(
        "http://localhost:5173,http://localhost:4173",
        description="Comma-separated browser origins allowed to call the UI API directly",
    )


settings = Settings()
