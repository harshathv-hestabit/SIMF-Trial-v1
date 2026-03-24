# SMIF

## v1.1 Checklist
- move modules' config to app/common and refactor docker services to use this path in bind mount []
- move `Client` indexing and upsert from MAS module to DPS module []
- Create proper model schemas for `Client` and `News` in DPS []
- Revise search.py in MAS module []
- Revise news_poller.py to use Benzinga realtime news wss api to poll news stream []

v1.1 planned flow for DPS module:

flowchart LR
    subgraph Source Layer
        NP[News Poller.py\nBronze News Input]
        PF[Portfolio.csv\nClient Portfolio Input]
    end

    subgraph DPS Processing Layer
        DPS[DPS Module v1.1\nProcess / Transform / Route]
    end

    subgraph Storage and Change Processing
        CDB[(Cosmos DB)]
        CFS[Change Feed Service]
    end

    subgraph Observability
        OBS[Streamlit Dashboard]
    end

    subgraph MAS Dispatch Layer
        EMD[Event Hub Dispatcher]
        SB[Service Bus]
        MAS[MAS]
    end

    NP -->|news input| DPS
    PF -->|client input| DPS

    DPS -->|upsert processed data| CDB
    CDB -->|change feed| CFS

    CFS -->|metrics / status| OBS
    CFS -->|processed event| EMD
    EMD --> SB
    SB --> MAS

## Description

Event-driven market insight system for ingesting market news, routing workflow events, matching news against client portfolios, and generating client-facing insights.

The project currently has three application modules:

- `DPS` ingests and transforms news, stores it in Cosmos DB, emits realtime events through Event Hub, and can publish standard workflow jobs to Service Bus.
- `EH_DISPATCHER` is an Azure Functions-based bridge that consumes Event Hub batches and republishes them to Service Bus queues.
- `MAS` consumes Service Bus queues, runs the portfolio matching and insight workflows, and stores generated insights.

The local stack is designed around Azure emulators, Elasticsearch, and Docker Compose.

## Current Architecture

```text
DPS Streamlit UI
  -> DPS pipeline
  -> Cosmos DB news container
  -> DPS change feed listener
  -> Event Hub: news-processed
  -> EH_DISPATCHER Azure Function
  -> Service Bus queue: realtime-news-events

DPS standard event publisher
  -> Service Bus queue: standard-news-events

MAS queue consumers
  -> HNW workflow for realtime_news
  -> Standard workflow for standard_news
  -> generate_insight events
  -> Insight workflow
  -> Cosmos DB insights container
  -> MAS Streamlit UI
```

Current routing behavior:

- `realtime_news` travels through Event Hub and is bridged into `realtime-news-events` queue.
- `standard_news` is published directly to `standard-news-events` queue.
- `generate_insight` is published directly to `generate-insight-events` queue.

Shared queue definitions live in [src/app/common/servicebus-config.json](/home/harshathvenkastesh/Desktop/SMIF/src/app/common/servicebus-config.json).

## Repository Layout

```text
src/
  .env.example
  .env.docker
  docker-compose.yaml
  requirements.txt
  app/
    common/
      __init__.py
      eventhub-config.json
      servicebus-config.json
      service_bus.py
    modules/
      DPS/
      EH_DISPATCHER/
      MAS/
README.md
```

## Components

### DPS

Relevant files:

- [src/app/modules/DPS/streamlit_app.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/DPS/streamlit_app.py)
- [src/app/modules/DPS/pipeline.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/DPS/pipeline.py)
- [src/app/modules/DPS/__main__.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/DPS/__main__.py)
- [src/app/modules/DPS/services/change_feed_service.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/DPS/services/change_feed_service.py)
- [src/app/modules/DPS/services/standard_event_service.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/DPS/services/standard_event_service.py)
- [src/app/modules/DPS/.dockerfile](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/DPS/.dockerfile)

Current role:

- Accepts raw market news through the Streamlit UI.
- Transforms source documents into the internal news schema.
- Writes news documents into Cosmos DB.
- Runs a Cosmos change-feed listener that emits realtime events into Event Hub.
- Publishes standard workflow jobs directly to Service Bus.
- In Docker, starts both the change-feed listener and the Streamlit UI in one container.

### EH_DISPATCHER

Relevant files:

- [src/app/modules/EH_DISPATCHER/__init__.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/EH_DISPATCHER/__init__.py)
- [src/app/modules/EH_DISPATCHER/function.json](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/EH_DISPATCHER/function.json)
- [src/app/modules/EH_DISPATCHER/host.json](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/EH_DISPATCHER/host.json)
- [src/app/modules/EH_DISPATCHER/local.settings.json.example](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/EH_DISPATCHER/local.settings.json.example)
- [src/app/modules/EH_DISPATCHER/.dockerfile](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/EH_DISPATCHER/.dockerfile)
- [src/app/common/service_bus.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/common/service_bus.py)

Current role:

- Runs as a Python Azure Function with an `eventHubTrigger`.
- Reads batched events from `%EVENTHUB_NAME%`.
- Maps supported `event_type` values to Service Bus queue names from the environment.
- Rebuilds payloads with shared transport metadata via `build_event_payload`.
- Publishes to Service Bus with retry logic.
- Is containerized as `eh_dispatcher` in Docker Compose.

### MAS

Relevant files:

- [src/app/modules/MAS/__main__.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/MAS/__main__.py)
- [src/app/modules/MAS/workflow/hnw.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/MAS/workflow/hnw.py)
- [src/app/modules/MAS/workflow/standard.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/MAS/workflow/standard.py)
- [src/app/modules/MAS/workflow/generate_insight.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/MAS/workflow/generate_insight.py)
- [src/app/modules/MAS/ui/main.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/MAS/ui/main.py)
- [src/app/modules/MAS/.dockerfile](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/MAS/.dockerfile)

Current role:

- Builds and indexes client portfolio data at startup.
- Consumes `realtime-news-events`, `standard-news-events`, and `generate-insight-events`.
- Runs the HNW workflow for `realtime_news`.
- Runs the standard workflow for `standard_news`.
- Runs the insight generation and verification workflow for `generate_insight`.
- Stores insights in Cosmos DB and serves them through the Streamlit UI.
- In Docker, starts both the MAS worker and the UI in one container.

## Local Infrastructure

[src/docker-compose.yaml](/home/harshathvenkastesh/Desktop/SMIF/src/docker-compose.yaml) currently defines:

- `azurite` for storage emulation and Azure Functions storage bindings
- `cosmos` for the Cosmos DB emulator
- `eventhub` for the Event Hubs emulator
- `servicebus-emulator` plus `mssql` for Service Bus queue emulation
- `elasticsearch` for client indexing and retrieval
- `dps` for the DPS listener and UI
- `mas` for the MAS workers and UI
- `eh_dispatcher` for the Event Hub -> Service Bus bridge

Default exposed ports:

- DPS UI: `http://localhost:8501`
- MAS UI: `http://localhost:8502`
- Elasticsearch: `http://localhost:9200`
- Cosmos emulator: `https://localhost:8081`
- Azurite Blob: `http://127.0.0.1:10000`
- Azurite Queue: `http://127.0.0.1:10001`
- Azurite Table: `http://127.0.0.1:10002`
- Event Hubs AMQP: `127.0.0.1:5672`
- Event Hubs Kafka endpoint: `127.0.0.1:9092`
- Service Bus AMQP: `127.0.0.2:5672`
- Service Bus management API: `http://127.0.0.2:5300`

## Running With Docker

Run from [src](/home/harshathvenkastesh/Desktop/SMIF/src):

```bash
docker compose up --build
```

This starts DPS, MAS, and EH_DISPATCHER alongside all required local infrastructure.

To stop and remove persisted emulator data:

```bash
docker compose down -v
```

## Running Locally Without Dockerized App Services

Create and activate a virtual environment from [src](/home/harshathvenkastesh/Desktop/SMIF/src):

```bash
cd src
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Start the infrastructure services

```bash
docker compose up azurite cosmos eventhub servicebus-emulator mssql elasticsearch
```

### 2. Configure environment files

Application modules load settings from `src/.env`.

Use [src/.env.example](/home/harshathvenkastesh/Desktop/SMIF/src/.env.example) as the baseline for:

- Cosmos DB settings
- Event Hub settings
- Service Bus settings
- Azure Storage settings
- queue names and workflow concurrency settings
- Elasticsearch settings
- LLM and data-provider credentials

The dispatcher function also provides a function-style settings example at [src/app/modules/EH_DISPATCHER/local.settings.json.example](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/EH_DISPATCHER/local.settings.json.example).

### 3. Start DPS

Run the DPS UI:

```bash
streamlit run app/modules/DPS/streamlit_app.py
```

Run the DPS change-feed listener:

```bash
python -m app.modules.DPS
```

### 4. Start EH_DISPATCHER

If you want to run the function locally instead of through Docker Compose, start it from [src/app/modules/EH_DISPATCHER](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/EH_DISPATCHER):

```bash
func start
```

### 5. Start MAS

Run MAS workers:

```bash
python -m app.modules.MAS
```

Run the MAS UI separately if needed:

```bash
streamlit run app/modules/MAS/ui/main.py --server.port 8502
```

## Configuration

### Shared transport helpers

Shared Service Bus utilities and payload helpers live in [src/app/common/service_bus.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/common/service_bus.py).

Shared emulator topology files live in:

- [src/app/common/eventhub-config.json](/home/harshathvenkastesh/Desktop/SMIF/src/app/common/eventhub-config.json)
- [src/app/common/servicebus-config.json](/home/harshathvenkastesh/Desktop/SMIF/src/app/common/servicebus-config.json)

### Settings definitions

Application settings are defined in:

- [src/app/modules/DPS/config/settings.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/DPS/config/settings.py)
- [src/app/modules/MAS/config/settings.py](/home/harshathvenkastesh/Desktop/SMIF/src/app/modules/MAS/config/settings.py)

Notable settings include:

- Cosmos DB connection and container names
- Event Hub connection settings
- Service Bus connection and queue names
- Azure Storage credentials
- workflow concurrency limits
- `SERVICEBUS_MAX_DELIVERY_ATTEMPTS`
- `ELASTICSEARCH_URL`
- `GOOGLE_API_KEY`, `GROQ_API_KEY`, `EODHD_API_KEY`, and `HF_TOKEN`

## Project Notes

- `src/.env` is required by the DPS and MAS settings loaders.
- `src/.env.docker` is used by the Docker Compose app containers.
- `EH_DISPATCHER` can run either in Docker Compose or under the local Azure Functions host.
- The current project phase is still hybrid: realtime workflow entry is Event Hub based, while standard and generate-insight paths are already Service Bus native.
- The current architecture diagram source is [docs/smif-current-phase.drawio](/home/harshathvenkastesh/Desktop/SMIF/docs/smif-current-phase.drawio).
