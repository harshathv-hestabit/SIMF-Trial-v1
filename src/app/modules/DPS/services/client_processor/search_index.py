from elasticsearch import Elasticsearch
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.modules.DPS.config.settings import settings


INDEX = "clients"
DIM = 384
EMBEDDING_MODEL = "models/gemini-embedding-2-preview"

INDEX_PROPERTIES = {
    "representation_type": {"type": "keyword"},
    "representation_version": {"type": "keyword"},
    "client_id": {"type": "keyword"},
    "client_name": {"type": "text"},
    "client_type": {"type": "keyword"},
    "client_segment": {"type": "keyword"},
    "client_segment_reason": {"type": "keyword"},
    "mandate": {"type": "keyword"},
    "total_aum_aed": {"type": "double"},
    "snapshot_id": {"type": "keyword"},
    "as_of": {"type": "date", "ignore_malformed": True},
    "holdings_count": {"type": "integer"},
    "asset_types": {"type": "keyword"},
    "asset_subtypes": {"type": "keyword"},
    "asset_classifications": {"type": "keyword"},
    "currencies": {"type": "keyword"},
    "asset_class_weights": {"type": "object", "enabled": False},
    "asset_type_weights": {"type": "object", "enabled": False},
    "broad_tags_of_interest": {"type": "keyword"},
    "major_tickers": {"type": "keyword"},
    "major_issuers": {"type": "text"},
    "major_sectors": {"type": "keyword"},
    "major_asset_descriptions": {"type": "text"},
    "compact_summary_text": {"type": "text"},
    "embedding": {
        "type": "dense_vector",
        "dims": DIM,
        "index": True,
        "similarity": "cosine",
    },
}

es = Elasticsearch(settings.ELASTICSEARCH_URL, verify_certs=False)
document_embedder = GoogleGenerativeAIEmbeddings(
    model=EMBEDDING_MODEL,
    api_key=settings.GOOGLE_API_KEY,
    task_type="RETRIEVAL_DOCUMENT",
    output_dimensionality=DIM,
)


def create_index() -> None:
    if es.indices.exists(index=INDEX).body:
        es.indices.put_mapping(index=INDEX, properties=INDEX_PROPERTIES)
        return

    es.indices.create(
        index=INDEX,
        settings={
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        mappings={"properties": INDEX_PROPERTIES},
    )


def index_client_documents(documents: list[dict]) -> None:
    create_index()
    for document in documents:
        es.index(
            index=INDEX,
            id=document["client_id"],
            document={
                **document,
                "embedding": _embed_document(_client_document_to_text(document)),
            },
        )


def _embed_document(text: str) -> list[float]:
    return document_embedder.embed_documents([text])[0]


def _client_document_to_text(document: dict) -> str:
    return " ".join(
        filter(
            None,
            [
                document.get("compact_summary_text", document.get("query", "")),
                " ".join(document.get("asset_classifications", [])),
                " ".join(document.get("major_asset_descriptions", [])),
                " ".join(document.get("major_issuers", [])),
                " ".join(document.get("major_tickers", [])),
                " ".join(document.get("currencies", [])),
                document.get("mandate", ""),
                document.get("client_type", ""),
            ],
        )
    )
