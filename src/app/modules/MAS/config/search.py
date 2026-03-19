from collections import defaultdict
from elasticsearch import Elasticsearch
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import math
import pandas as pd
import requests
import json
import time
from pathlib import Path
from .settings import settings
from .client import build_all_client_profiles, ClientProfile
from .client_portfolio_store import insert_clients_to_cosmos

PORTFOLIO_PATH = Path(__file__).resolve().parent / "portfolio.csv"

es = Elasticsearch(settings.ELASTICSEARCH_URL, verify_certs=False)
INDEX = "clients"
DIM = 384
CACHE_FILE = Path(__file__).resolve().parent / "isin_to_ticker.json"
EMBEDDING_MODEL = "models/gemini-embedding-001"

document_embedder = GoogleGenerativeAIEmbeddings(
    model=EMBEDDING_MODEL,
    api_key=settings.GOOGLE_API_KEY,
    task_type="RETRIEVAL_DOCUMENT",
    output_dimensionality=DIM,
)
query_embedder = GoogleGenerativeAIEmbeddings(
    model=EMBEDDING_MODEL,
    api_key=settings.GOOGLE_API_KEY,
    task_type="RETRIEVAL_QUERY",
    output_dimensionality=DIM,
)


def _normalize_embedding(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if not magnitude:
        return vector
    return [value / magnitude for value in vector]


def _embed_document(text: str) -> list[float]:
    return _normalize_embedding(document_embedder.embed_documents([text])[0])


def _embed_query(text: str) -> list[float]:
    return _normalize_embedding(query_embedder.embed_query(text))

def build_isin_ticker_map(isins: list[str]) -> dict[str, str]:
    if CACHE_FILE.exists():
        cached = json.loads(CACHE_FILE.read_text())
        missing = [i for i in isins if i not in cached]
        if not missing:
            print(f"[FIGI] Loaded {len(cached)} mappings from cache.")
            return cached
        print(f"[FIGI] Cache hit for {len(cached)}, fetching {len(missing)} new ISINs...")
        isins = missing
    else:
        cached = {}

    mapping = {}
    batch_size = 10
    for i in range(0, len(isins), batch_size):
        batch = isins[i:i + batch_size]
        jobs = [{"idType": "ID_ISIN", "idValue": isin} for isin in batch]
        resp = requests.post(
            "https://api.openfigi.com/v3/mapping",
            json=jobs,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        for isin, result in zip(batch, resp.json()):
            for hit in result.get("data", []):
                ticker = hit.get("ticker")
                if ticker:
                    mapping[isin] = ticker.upper()
                    break  
        time.sleep(5)

    merged = {**cached, **mapping}
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(merged, indent=2))
    print(f"[FIGI] Cached {len(merged)} total ISIN→ticker mappings.")
    return merged

def create_index() -> None:
    if es.indices.exists(index=INDEX).body:
        print(f"Index '{INDEX}' already exists.")
        return

    es.indices.create(
        index=INDEX,
        settings={
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        mappings={
            "properties": {
                "client_id":              {"type": "keyword"},
                "client_name":            {"type": "text"},
                "client_type":            {"type": "keyword"},
                "mandate":                {"type": "keyword"},
                "total_aum_aed":          {"type": "double"},
                "asset_types":            {"type": "keyword"},
                "asset_subtypes":         {"type": "keyword"},
                "asset_classifications":  {"type": "keyword"},
                "currencies":             {"type": "keyword"},
                "isins":                  {"type": "keyword"},
                "ticker_symbols":         {"type": "keyword"},
                "asset_ids":              {"type": "keyword"},
                "asset_descriptions":     {"type": "text"},
                "classification_weights": {"type": "object", "enabled": False},
                "asset_type_weights":     {"type": "object", "enabled": False},
                "query":                  {"type": "text"},
                "tags_of_interest":       {"type": "keyword"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": DIM,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        }
    )
    print(f"Index '{INDEX}' created.")

def recreate_index() -> None:
    if es.indices.exists(index=INDEX).body:
        es.indices.delete(index=INDEX)
        print(f"Index '{INDEX}' deleted.")
    create_index()

def _profile_to_text(client: ClientProfile) -> str:
    return " ".join(filter(None, [
        client.query,
        " ".join(client.asset_classifications),
        " ".join(client.asset_descriptions[:20]),
        " ".join(client.currencies),
        client.mandate,
        client.client_type,
    ]))


def attach_ticker_symbols(
    profiles: dict[str, ClientProfile],
    isin_ticker_map: dict[str, str],
) -> None:
    for profile in profiles.values():
        profile.ticker_symbols = list(filter(None, [
            isin_ticker_map.get(isin) for isin in profile.isins
        ]))

def index_client(client: ClientProfile, isin_ticker_map: dict[str, str]) -> None:
    text = _profile_to_text(client)
    embedding = _embed_document(text)

    es.index(
        index=INDEX,
        id=client.client_id,
        document={
            "client_id":              client.client_id,
            "client_name":            client.client_name,
            "client_type":            client.client_type,
            "mandate":                client.mandate,
            "total_aum_aed":          client.total_aum_aed,
            "asset_types":            client.asset_types,
            "asset_subtypes":         client.asset_subtypes,
            "asset_classifications":  client.asset_classifications,
            "currencies":             client.currencies,
            "isins":                  client.isins,
            "ticker_symbols":         client.ticker_symbols,
            "asset_ids":              client.asset_ids,
            "asset_descriptions":     client.asset_descriptions,
            "classification_weights": client.classification_weights,
            "asset_type_weights":     client.asset_type_weights,
            "query":                  client.query,
            "tags_of_interest":       client.tags_of_interest,
            "embedding":              embedding,
        }
    )
    print(f"Client '{client.client_name}' (id={client.client_id}) "
          f"indexed with {len(client.ticker_symbols)} tickers.")

def _news_to_text(doc: dict) -> str:
    return " ".join(filter(None, [
        doc.get("title", ""),
        doc.get("content", ""),
        " ".join(doc.get("tags", [])),
        " ".join(doc.get("symbols", [])),
    ]))

def score_news_against_clients(
    news_doc: dict,
    top_k: int = 5,
    min_score: float = 0.0,
) -> list[dict]:
    news_text    = _news_to_text(news_doc)
    news_vec     = _embed_query(news_text)
    news_tags    = [t.upper() for t in news_doc.get("tags", [])]
    news_tickers = [s.split(".")[0].upper() for s in news_doc.get("symbols", [])]
    print(f"[DEBUG] news_tickers: {news_tickers}")
    print(f"[DEBUG] news_tags: {news_tags}")
    
    knn_response = es.search(
        index=INDEX,
        size=top_k,
        knn={
            "field":          "embedding",
            "query_vector":   news_vec,
            "k":              top_k,
            "num_candidates": 100,
        },
        source={"excludes": ["embedding"]},
    )

    bm25_response = es.search(
        index=INDEX,
        size=top_k,
        query={
            "bool": {
                "should": [
                    {"terms": {"ticker_symbols":    news_tickers, "boost": 3.0}},  # UPDATED
                    {"terms": {"tags_of_interest":  news_tags,    "boost": 1.5}},
                    {"match": {"asset_descriptions": {"query": news_text, "boost": 1.0}}},
                    {"match": {"query":              {"query": news_text, "boost": 0.8}}},
                ],
                "minimum_should_match": 1,
            }
        },
        source={"excludes": ["embedding"]},
    )

    RRF_K = 60
    rrf_scores: dict[str, float] = defaultdict(float)
    hit_sources: dict[str, dict] = {}

    for rank, hit in enumerate(knn_response["hits"]["hits"], start=1):
        cid = hit["_source"]["client_id"]
        rrf_scores[cid] += 1 / (RRF_K + rank)
        hit_sources[cid] = hit["_source"]

    for rank, hit in enumerate(bm25_response["hits"]["hits"], start=1):
        cid = hit["_source"]["client_id"]
        rrf_scores[cid] += 1 / (RRF_K + rank)
        hit_sources.setdefault(cid, hit["_source"])

    max_rrf = max(rrf_scores.values(), default=1.0)

    results = []
    for cid, raw_score in sorted(rrf_scores.items(), key=lambda x: -x[1]):
        normalized_score = round(raw_score / max_rrf, 4)
        if normalized_score < min_score:
            continue

        source = hit_sources[cid]
        client_tickers = [t.upper() for t in source.get("ticker_symbols", [])]
        client_tags    = [t.upper() for t in source.get("tags_of_interest", [])]

        results.append({
            "client_id":               cid,
            "client_name":             source["client_name"],
            "relevance_score":         normalized_score,
            "matched_isins":           list(set(client_tickers) & set(news_tickers)),
            "matched_tags":            list(set(client_tags) & set(news_tags)),
            "matched_classifications": source.get("asset_classifications", []),
            "classification_weights":  source.get("classification_weights", {}),
        })

        if len(results) >= top_k:
            break

    return results

def process_news_stream(
    news_docs: list[dict],
    top_k: int = 5,
    min_score: float = 0.0,
) -> dict[str, list[dict]]:
    results = {}
    for doc in news_docs:
        news_id = doc.get("id", doc.get("title", "unknown"))
        matched_clients = score_news_against_clients(doc, top_k=top_k, min_score=min_score)
        if matched_clients:
            results[news_id] = matched_clients
            print(f"\nNews: {doc.get('title', '')[:60]}...")
            for match in matched_clients:
                print(
                    f"  → [{match['relevance_score']:.4f}] "
                    f"client={match['client_name']} (id={match['client_id']}) "
                    f"tickers={match['matched_isins']} "
                    f"tags={match['matched_tags']}"
                )
    return results

import asyncio

async def run_indexing():
    df = pd.read_csv(PORTFOLIO_PATH)
    profiles = build_all_client_profiles(df)
    all_isins = list({isin for p in profiles.values() for isin in p.isins})
    print(f"[Setup] {len(all_isins)} unique ISINs across {len(profiles)} clients")

    isin_ticker_map = build_isin_ticker_map(all_isins)
    attach_ticker_symbols(profiles, isin_ticker_map)
    create_index()

    for profile in profiles.values():
        index_client(profile, isin_ticker_map)
        
    await insert_clients_to_cosmos(profiles)
