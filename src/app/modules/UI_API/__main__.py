import uvicorn

from .settings import settings


if __name__ == "__main__":
    uvicorn.run(
        "app.modules.UI_API.main:app",
        host="0.0.0.0",
        port=settings.UI_API_PORT,
        log_level="info",
    )
