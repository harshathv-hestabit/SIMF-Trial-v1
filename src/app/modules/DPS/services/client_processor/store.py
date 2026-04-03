from app.common.portfolio_schema import build_holdings_container_name
from app.common.azure_services.cosmos import build_async_cosmos_client, ensure_async_container
from app.common.mongo_backup import backup_document_async
from app.modules.DPS.config.settings import settings


async def upsert_client_representations(
    profile_documents: list[dict],
    holdings_snapshots: list[dict],
) -> None:
    async with build_async_cosmos_client(settings.COSMOS_URL, settings.COSMOS_KEY) as client:
        profile_container = await ensure_async_container(
            client,
            database_name=settings.COSMOS_DB,
            container_name=settings.CLIENT_PORTFOLIO_CONTAINER,
            partition_key_path=settings.CLIENT_PORTFOLIO_CONTAINER_PARTITION_ID,
        )
        holdings_container_name = build_holdings_container_name(
            settings.CLIENT_PORTFOLIO_CONTAINER
        )
        holdings_container = await ensure_async_container(
            client,
            database_name=settings.COSMOS_DB,
            container_name=holdings_container_name,
            partition_key_path=settings.CLIENT_PORTFOLIO_CONTAINER_PARTITION_ID,
        )

        for document in profile_documents:
            await profile_container.upsert_item(document)
            await backup_document_async(
                settings,
                collection_name=settings.CLIENT_PORTFOLIO_CONTAINER,
                document=document,
            )

        for document in holdings_snapshots:
            await holdings_container.upsert_item(document)
            await backup_document_async(
                settings,
                collection_name=holdings_container_name,
                document=document,
            )


async def upsert_client_profiles(documents: list[dict]) -> None:
    await upsert_client_representations(documents, [])
