<!-- # SIMF-Trial-v1
SIMF Trial Implementation V1: Event Driven System

Current Progress:
1. Data Pipeline System:
 - config/_cosmosdb.py: For Cosmos db config. Contains the config for Database, News container along with URL and primary key for the cosmos client
 - config/_eventhub.py: contains the eventhub config and a eventhub producer client initialization function
 - services/change_feed_service.py: contains implementation that uses cosmos change feed service on news container + event producer client to add an event to the eventhub for every news document inserted in the container
 - ingestion/_ingestion_service.py: currently a stub implementation for ingesting documents. returns an array of documents
 - transformation/_transform.py: a stub implementation for processing the ingested news documents and returning the documents in specified format that contains title, content, tags
 - pipeline.py: the main pipeline used for ingestion-transformation-cosmos upsert flow
 - app.py: a streamlit interface to allow upload of news document (single/multiple) json format.

 2. Multi Agent System:
 - main.py: the main script that runs the eventhub consumer client as service and watches the eventhub for any events. contains implementation to process events using eventtype. No orchestrator has been used for now
 - config/_azure_blob_storage.py: contains blob service client that is used by the eventhub consumer client to store event checkpoints
 - config/_eventhub.py: contains the eventhub config and a eventhub consumer initialization function with azure blobcheckpoint support
 - config/_search.py: supports search and relevance score using Elastic search. this file contains the implementation for indexing client portfolios and performing search related operations against the client index. 
 - config/_client.py: client portfolio schema model config for processing raw client portfolio detail
 - util/event_executor.py: implementation for event executor function used in the HNW workflow for adding the 'generate_insight' events to the eventhub
 - workflow/hnw.py: prototype hnw workflow without agent. Currently supports reading news event data, fetching client portfolio data from cosmos db container using function nodes.
 - workflow/generate_insight.py: stub implementation for representing insight generation flow. Work in progress here
 - workflow/standard.py: stub implementation for standard clients
 

 3. docker-compose.yaml
 - contains the config for services that allow implementation of azure services using emulators.
 - the services that are used: 
    Azurite - primarily for storing eventhub checkpoints
    Eventhub emulator - allowing for event driven system implementation
    Cosmos db emulator - for storing news, portfolio and insights in their respective containers
    Elastic Search - used as an alternative to Azure AI search for retrieval and relevance scoring
    
     -->

# SIMF-Trial-v1

SIMF Trial Implementation V1: Event Driven System
---

## Overview

The current system follows a pipeline + event-driven workflow architecture:

* **Data Pipeline** → Ingest → Transform → Store (Cosmos DB) → Emit Events
* **Event System (MAS)** → Consume Events → Execute Workflows → Generate Insights

---

## Current Progress

### 1. Data Pipeline System

Responsible for ingesting raw news data, transforming it, storing it, and emitting events for downstream processing.

#### Configuration

* `config/_cosmosdb.py`
  Initializes Cosmos DB client and defines:

  * Database configuration
  * News container
  * Connection parameters (URL, primary key)

* `config/_eventhub.py`

  * Event Hub configuration
  * Producer client initialization

#### Core Services

* `services/change_feed_service.py`
  Implements Cosmos DB Change Feed:

  * Listens to inserts in the **news container**
  * Emits an event to Event Hub for every new document

#### Pipeline Stages

* `ingestion/_ingestion_service.py`

  * Stub implementation
  * Returns a list of raw news documents

* `transformation/_transform.py`

  * Stub transformation layer
  * Outputs structured documents with:

    * `title`
    * `content`
    * `tags`

* `pipeline.py`
  Orchestrates:

  * Ingestion
  * Transformation
  * Cosmos DB upsert

#### Interface

* `app.py`

  * Streamlit-based UI
  * Supports upload of single/multiple JSON files
  * Triggers pipeline execution

---

### 2. Multi-Agent System (Event-Driven Execution Layer)

Handles event consumption and workflow execution.
Current design is **event-type driven**, without a formal orchestrator (yet).

#### Entry Point

* `main.py`

  * Runs Event Hub consumer client as a service
  * Listens for incoming events
  * Routes processing based on `event_type`

#### Configuration

* `config/_azure_blob_storage.py`

  * Blob storage client
  * Used for Event Hub checkpointing

* `config/_eventhub.py`

  * Consumer client initialization
  * Integrated with Blob checkpoint store

* `config/_search.py`

  * Elasticsearch integration
  * Supports:

    * Client portfolio indexing
    * Relevance-based search

* `config/_client.py`

  * Client portfolio schema/model
  * Used to structure raw client data

#### Execution Layer

* `util/event_executor.py`

  * Executes workflow steps
  * Emits downstream events (e.g., `generate_insight`)

#### Workflows

* `workflow/hnw.py`
  Prototype workflow for High Net Worth (HNW) clients:

  * Reads news event
  * Fetches client portfolio from Cosmos DB
  * Uses function-node-based execution

* `workflow/generate_insight.py`

  * Stub for insight generation logic
  * Under development

* `workflow/standard.py`

  * Stub workflow for standard clients

---

### 3. Infrastructure (Dockerized Local Setup)

* `docker-compose.yaml`

Provides local emulation of Azure services:

* **Azurite**

  * Used for Event Hub checkpoint storage

* **Event Hub Emulator**

  * Enables local event-driven architecture

* **Cosmos DB Emulator**

  * Stores:

    * News
    * Client portfolios
    * Insights

* **Elasticsearch**

  * Used as an alternative to Azure AI Search
  * Handles retrieval and relevance scoring

---

## Architecture Summary

```
[Streamlit UI]
        ↓
[Ingestion Service]
        ↓
[Transformation Layer]
        ↓
[Cosmos DB (News Container)]
        ↓ (Change Feed)
[Event Hub]
        ↓
[Event Consumer (MAS)]
        ↓
[Workflows (HNW / Standard)]
        ↓
[Insight Generation]
```

---

## Current Limitations

* Multiple components are still **stub implementations**
* No centralized **workflow orchestrator** (event-type routing used instead)
* Insight generation logic is incomplete
---

## Next tasks

* complete the implementation of  full **insight generation pipeline**
* Optimize **event fan-out and Cosmos DB reads**
* Improve **client-news relevance mapping**
---