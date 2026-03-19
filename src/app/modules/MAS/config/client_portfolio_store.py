from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey

from .client import ClientProfile
from .settings import settings

async def insert_clients_to_cosmos(profiles: dict[str, ClientProfile]) -> None:
    async with CosmosClient(
        settings.COSMOS_URL,
        credential=settings.COSMOS_KEY,
        connection_verify=False,
        enable_endpoint_discovery=False,
        connection_timeout=5,
    ) as client:
        db = client.get_database_client(settings.COSMOS_DB)
        try:
            container = await db.create_container_if_not_exists(
                id=settings.CLIENT_PORTFOLIO_CONTAINER,
                partition_key=PartitionKey(
                    path=settings.CLIENT_PORTFOLIO_CONTAINER_PARTITION_ID
                ),
            )
        except Exception:
            container = db.get_container_client(settings.CLIENT_PORTFOLIO_CONTAINER)

        print(f"[Cosmos] Using container '{settings.CLIENT_PORTFOLIO_CONTAINER}'")
        for profile in profiles.values():
            doc = {
                "id": profile.client_id,
                "client_id": profile.client_id,
                "client_name": profile.client_name,
                "client_type": profile.client_type,
                "mandate": profile.mandate,
                "total_aum_aed": profile.total_aum_aed,
                "asset_types": profile.asset_types,
                "asset_subtypes": profile.asset_subtypes,
                "asset_classifications": profile.asset_classifications,
                "currencies": profile.currencies,
                "isins": profile.isins,
                "ticker_symbols": profile.ticker_symbols,
                "asset_ids": profile.asset_ids,
                "asset_descriptions": profile.asset_descriptions,
                "classification_weights": profile.classification_weights,
                "asset_type_weights": profile.asset_type_weights,
                "query": profile.query,
                "tags_of_interest": profile.tags_of_interest,
            }
            await container.upsert_item(doc)
        print(f"[Cosmos] Inserted/Updated {len(profiles)} client portfolios")
