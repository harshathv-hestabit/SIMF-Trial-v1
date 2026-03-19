# SMIF

Event-driven market insight pipeline with two application modules:

- `DPS` ingests raw news JSON, transforms it, stores it in Cosmos DB, and emits realtime events.
- `MAS` indexes client portfolios, matches news to clients, generates insights, verifies them, and stores the resulting insight documents.

The project is designed to run locally with Azure emulators plus Elasticsearch through Docker Compose.

## Repository Layout

```text
src/
  docker-compose.yaml
  requirements.txt
  .env.example
  app/
    modules/
      DPS/
        streamlit_app.py
        pipeline.py
        services/change_feed_service.py
        news_raw/
      MAS/
        __main__.py
        ui/main.py
        workflow/
        agents/
        config/
```

## Current Architecture

```text
DPS Streamlit UI
  -> pipeline
  -> transform raw news
  -> Cosmos DB news container
  -> Cosmos change feed listener
  -> Event Hub event: realtime_news
  -> MAS consumer
  -> HNW workflow
  -> Elasticsearch client matching
  -> Event Hub event: generate_insight
  -> Insight generation + verification graph
  -> Cosmos DB insights container
  -> MAS Streamlit UI
```

## Services

### DPS

Main files:

- [src/app/modules/DPS/streamlit_app.py](./src/app/modules/DPS/streamlit_app.py)
- [src/app/modules/DPS/pipeline.py](./src/app/modules/DPS/pipeline.py)
- [src/app/modules/DPS/services/change_feed_service.py](./src/app/modules/DPS/services/change_feed_service.py)

Current behavior:

- Streamlit UI accepts uploaded JSON files or runs the sample documents in `news_raw/`.
- `pipeline.py` transforms each raw article into the internal news document schema and upserts it into Cosmos DB.
- Each pipeline run writes a timestamped log file under `src/app/modules/DPS/logs/`.
- `python -m app.modules.DPS` runs the change-feed listener, which watches the Cosmos news container and publishes `realtime_news` events to Event Hub.

Transformed news documents include:

- `id`
- `type`
- `title`
- `content`
- `link`
- `symbols`
- `tags`
- `sentiment`
- `source`
- `published_at`
- `fetched_at`
- `query_symbol`
- `processed_at`

### MAS

Main files:

- [src/app/modules/MAS/__main__.py](./src/app/modules/MAS/__main__.py)
- [src/app/modules/MAS/config/search.py](./src/app/modules/MAS/config/search.py)
- [src/app/modules/MAS/workflow/hnw.py](./src/app/modules/MAS/workflow/hnw.py)
- [src/app/modules/MAS/workflow/generate_insight.py](./src/app/modules/MAS/workflow/generate_insight.py)
- [src/app/modules/MAS/ui/main.py](./src/app/modules/MAS/ui/main.py)

Current behavior:

- On startup, MAS runs client indexing before it starts consuming Event Hub events.
- Client portfolios are built from `config/portfolio.csv`.
- ISINs are mapped to tickers through OpenFIGI and cached in `config/isin_to_ticker.json`.
- Client profiles are embedded with Google embeddings (`models/gemini-embedding-001`) and indexed in Elasticsearch.
- Enriched client portfolio documents are also persisted to Cosmos DB.
- MAS consumes Event Hub events and routes them by `event_type`.
- `realtime_news` currently triggers the HNW workflow.
- The HNW workflow fetches the news document from Cosmos, scores it against indexed client portfolios, fetches matched client documents, and emits `generate_insight` events.
- The insight workflow generates an insight draft, verifies it, and persists the result to the Cosmos insights container.
- The MAS Streamlit UI shows insights by `client_id`.

## UIs

### DPS UI

- Title: `Smart Market Insight Feed`
- Entry: [src/app/modules/DPS/streamlit_app.py](./src/app/modules/DPS/streamlit_app.py)
- Default port in Docker: `8501`

### MAS UI

- Title: `SMIF Clients`
- Entry: [src/app/modules/MAS/ui/main.py](./src/app/modules/MAS/ui/main.py)
- Default port in Docker: `8502`
- Loads available clients from Cosmos and displays all stored insights for the selected client

## Local Infrastructure

[src/docker-compose.yaml](./src/docker-compose.yaml) defines:

- `azurite` for Event Hub checkpoint storage
- `cosmos` for the Cosmos DB emulator
- `eventhub` for the Event Hubs emulator
- `elasticsearch` for client profile indexing and retrieval
- `dps` for the DPS listener + Streamlit UI
- `mas` for the MAS consumer + Streamlit UI

Both application images install dependencies from the shared [src/requirements.txt](./src/requirements.txt).

## Running With Docker

Run these commands from `src/`:

```bash
docker compose up --build
```

Useful endpoints:

- DPS UI: `http://localhost:8501`
- MAS UI: `http://localhost:8502`
- Elasticsearch: `http://localhost:9200`
- Cosmos emulator: `https://localhost:8081`

To reset everything, including emulator and Elasticsearch data:

```bash
docker compose down -v
```

## Running Locally

Create a virtual environment, install shared dependencies, and work from `src/`:

```bash
python3 -m venv demo
source demo/bin/activate
pip install -r requirements.txt
```

Run DPS Streamlit:

```bash
streamlit run app/modules/DPS/streamlit_app.py
```

Run MAS service:

```bash
python -m app.modules.MAS
```

Run MAS UI separately:

```bash
streamlit run app/modules/MAS/ui/main.py
```

Run the DPS change-feed listener:

```bash
python -m app.modules.DPS
```

## Environment Variables

The application settings are defined in:

- [src/app/modules/DPS/config/settings.py](./src/app/modules/DPS/config/settings.py)
- [src/app/modules/MAS/config/settings.py](./src/app/modules/MAS/config/settings.py)

The example file is:

- [src/.env.example](./src/.env.example)

Required variables from code:

- `GROQ_API_KEY`
- `GROQ_BASE_URL`
- `COSMOS_URL`
- `COSMOS_KEY`
- `COSMOS_DB`
- `NEWS_CONTAINER`
- `NEWS_CONTAINER_PARTITION_ID`
- `CLIENT_PORTFOLIO_CONTAINER`
- `CLIENT_PORTFOLIO_CONTAINER_PARTITION_ID`
- `INSIGHTS_CONTAINER`
- `INSIGHTS_CONTAINER_PARTITION_ID`
- `EVENTHUB_NAME`
- `EVENTHUB_CONNECTION_STRING`
- `CHECKPOINT_CONTAINER`
- `AZURE_STORAGE_ACCOUNT`
- `AZURE_STORAGE_KEY`
- `AZURE_STORAGE_CONNECTION_STRING`
- `EODHD_API_KEY`
- `HF_TOKEN`
- `GOOGLE_API_KEY`
- `ELASTICSEARCH_URL`

Note:

- `src/.env.example` is currently incomplete relative to the settings classes. `GOOGLE_API_KEY` and `ELASTICSEARCH_URL` are required by MAS even though they are not present in the example file.

## Data Sources and Storage

### News Input

- Raw sample articles live in [src/app/modules/DPS/news_raw](./src/app/modules/DPS/news_raw)
- Additional raw news can be fetched using [src/app/sample_insert.py](./src/app/sample_insert.py)

### Client Data

- Raw client portfolio CSV: [src/app/modules/MAS/config/portfolio.csv](./src/app/modules/MAS/config/portfolio.csv)
- Cached ISIN to ticker mapping: [src/app/modules/MAS/config/isin_to_ticker.json](./src/app/modules/MAS/config/isin_to_ticker.json)

### Cosmos Containers

Expected containers:

- news
- client portfolio
- insights

Container names and partition keys are driven by environment variables.

## Search and Matching

Client matching is implemented in [src/app/modules/MAS/config/search.py](./src/app/modules/MAS/config/search.py).

Current approach:

- generate client profile embeddings with `gemini-embedding-001`
- generate query embeddings for incoming news
- run Elasticsearch KNN search on the dense vector
- run a parallel lexical query using ticker and tag overlap
- fuse the two result sets with reciprocal rank fusion

This module also:

- creates the `clients` Elasticsearch index
- enriches client profiles with ticker symbols before persistence
- writes client portfolio documents to Cosmos after enrichment

## Known Limitations

These are current codebase limitations, not planned behavior:

- MAS startup is coupled to successful client indexing. If OpenFIGI lookup fails and the cache is incomplete, MAS startup fails.
- The insight generation prompts are still rough. The generator currently injects `news["symbols"]` into the `Content` section, and the verifier still expects `news["tickers"]` / `portfolio["holdings"]`, which do not fully align with the current stored document shapes.
- DPS pipeline failure handling still fails the whole run on an upsert exception.
- Cosmos connections run with certificate verification disabled for emulator compatibility.
- `docker compose down -v` removes Elasticsearch data, so MAS must rebuild the client index on the next startup.

## Current Status

What is working now:

- Dockerized local stack with Azure emulators and Elasticsearch
- DPS Streamlit ingestion flow
- Cosmos-backed change-feed listener
- Event Hub fan-out from DPS to MAS
- Client profile construction and Elasticsearch indexing
- Google-embedding-based client matching
- Insight persistence to Cosmos
- MAS Streamlit insight viewer by client

What is still evolving:

- standard-client workflow depth
- prompt quality and verifier accuracy
- OpenFIGI failure handling and startup resilience
- more robust DPS pipeline retry / partial-failure handling
