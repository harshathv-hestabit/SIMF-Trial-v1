COSMOSDB_CONFIG = {
    "database_name": "SMIF",
    "containers": [
        {
            "name": "news",
            "partition_key": "/id",
        }
    ],
}

DATABASE_NAME = COSMOSDB_CONFIG["database_name"]
NEWS_CONTAINER = COSMOSDB_CONFIG["containers"][0]["name"]
NEWS_PARTITION_KEY = COSMOSDB_CONFIG["containers"][0]["partition_key"]