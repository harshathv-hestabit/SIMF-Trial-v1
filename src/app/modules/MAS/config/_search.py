# from elasticsearch import Elasticsearch
# from elasticsearch.helpers import bulk
# from sentence_transformers import SentenceTransformer
# from dataclasses import dataclass, field
# from collections import defaultdict
# import pandas as pd
# from ._client import build_all_client_profiles, ClientProfile
# es = Elasticsearch("http://localhost:9200", verify_certs=False)
# embedder = SentenceTransformer("all-MiniLM-L6-v2")

# INDEX = "clients"
# DIM = 384
# def create_index() -> None:
#     if es.indices.exists(index=INDEX).body:
#         print(f"Index '{INDEX}' already exists.")
#         return

#     es.indices.create(
#         index=INDEX,
#         settings={
#             "number_of_shards": 1,
#             "number_of_replicas": 0,
#         },
#         mappings={
#             "properties": {
#                 # Identity
#                 "client_id":              {"type": "keyword"},
#                 "client_name":            {"type": "text"},
#                 "client_type":            {"type": "keyword"},
#                 "mandate":                {"type": "keyword"},
#                 "total_aum_aed":          {"type": "double"},

#                 # Portfolio dimensions — keyword for exact matching
#                 "asset_types":            {"type": "keyword"},
#                 "asset_subtypes":         {"type": "keyword"},
#                 "asset_classifications":  {"type": "keyword"},
#                 "currencies":             {"type": "keyword"},
#                 "isins":                  {"type": "keyword"},
#                 "asset_ids":              {"type": "keyword"},

#                 # Asset names — text for BM25 matching against news content
#                 "asset_descriptions":     {"type": "text"},

#                 # Weights — stored but not indexed (used in response only)
#                 "classification_weights": {"type": "object", "enabled": False},
#                 "asset_type_weights":     {"type": "object", "enabled": False},

#                 # Semantic fields
#                 "query":                  {"type": "text"},
#                 "tags_of_interest":       {"type": "keyword"},

#                 # Vector
#                 "embedding": {
#                     "type": "dense_vector",
#                     "dims": DIM,
#                     "index": True,
#                     "similarity": "cosine",
#                 },
#             }
#         }
#     )
#     print(f"Index '{INDEX}' created.")

# def _profile_to_text(client: ClientProfile) -> str:
#     """Flatten profile into text for embedding."""
#     return " ".join(filter(None, [
#         client.query,
#         " ".join(client.asset_classifications),
#         " ".join(client.asset_descriptions[:20]),
#         " ".join(client.currencies),
#         client.mandate,
#         client.client_type,
#     ]))

# def index_client(client: ClientProfile) -> None:
#     """Upsert a client profile. Called once per client, or on profile change."""
#     text = _profile_to_text(client)
#     embedding = embedder.encode([text], normalize_embeddings=True)[0].tolist()

#     es.index(
#         index=INDEX,
#         id=client.client_id,
#         document={
#             "client_id":              client.client_id,
#             "client_name":            client.client_name,
#             "client_type":            client.client_type,
#             "mandate":                client.mandate,
#             "total_aum_aed":          client.total_aum_aed,
#             "asset_types":            client.asset_types,
#             "asset_subtypes":         client.asset_subtypes,
#             "asset_classifications":  client.asset_classifications,
#             "currencies":             client.currencies,
#             "isins":                  client.isins,
#             "asset_ids":              client.asset_ids,
#             "asset_descriptions":     client.asset_descriptions,
#             "classification_weights": client.classification_weights,
#             "asset_type_weights":     client.asset_type_weights,
#             "query":                  client.query,
#             "tags_of_interest":       client.tags_of_interest,
#             "embedding":              embedding,
#         }
#     )
#     print(f"Client '{client.client_name}' (id={client.client_id}) indexed.")

# def _news_to_text(doc: dict) -> str:
#     return " ".join(filter(None, [
#         doc.get("title", ""),
#         doc.get("content", ""),
#         " ".join(doc.get("tags", [])),
#         " ".join(doc.get("symbols", [])),
#     ]))

# def score_news_against_clients(
#     news_doc: dict,
#     top_k: int = 5,
#     min_score: float = 0.0,
# ) -> list[dict]:
#     news_text    = _news_to_text(news_doc)
#     news_vec     = embedder.encode([news_text], normalize_embeddings=True)[0].tolist()
#     news_symbols = [s.upper() for s in news_doc.get("symbols", [])]
#     news_tags    = [t.upper() for t in news_doc.get("tags", [])]
#     # Add temporarily to score_news_against_clients, after news_symbols/news_tags are set
#     print(f"[DEBUG] news_symbols: {news_symbols}")
#     print(f"[DEBUG] news_tags: {news_tags}")
#     # --- KNN pass (semantic similarity, score is cosine 0–1) ---
#     knn_response = es.search(
#         index=INDEX,
#         size=top_k,
#         knn={
#             "field":        "embedding",
#             "query_vector": news_vec,
#             "k":            top_k,
#             "num_candidates": 100,
#         },
#         source={"excludes": ["embedding"]},
#     )

#     # --- BM25 / keyword pass ---
#     bm25_response = es.search(
#         index=INDEX,
#         size=top_k,
#         query={
#             "bool": {
#                 "should": [
#                     {"terms": {"isins":            news_symbols, "boost": 3.0}},
#                     {"terms": {"asset_ids":         news_symbols, "boost": 2.5}},
#                     {"terms": {"tags_of_interest":  news_tags,    "boost": 1.5}},
#                     {"match": {"asset_descriptions": {"query": news_text, "boost": 1.0}}},
#                     {"match": {"query":              {"query": news_text, "boost": 0.8}}},
#                 ],
#                 "minimum_should_match": 1,
#             }
#         },
#         source={"excludes": ["embedding"]},
#     )

#     # --- Reciprocal Rank Fusion (RRF) --- 
#     # score(d) = Σ 1 / (k + rank)  where k=60 is standard
#     RRF_K = 60
#     rrf_scores: dict[str, float] = defaultdict(float)
#     hit_sources: dict[str, dict] = {}

#     for rank, hit in enumerate(knn_response["hits"]["hits"], start=1):
#         cid = hit["_source"]["client_id"]
#         rrf_scores[cid] += 1 / (RRF_K + rank)
#         hit_sources[cid] = hit["_source"]

#     for rank, hit in enumerate(bm25_response["hits"]["hits"], start=1):
#         cid = hit["_source"]["client_id"]
#         rrf_scores[cid] += 1 / (RRF_K + rank)
#         hit_sources.setdefault(cid, hit["_source"])

#     # Normalize RRF scores to 0–1 (max possible is 2/61 ≈ 0.0328 if rank=1 in both)
#     max_rrf = max(rrf_scores.values(), default=1.0)
    
#     results = []
#     for cid, raw_score in sorted(rrf_scores.items(), key=lambda x: -x[1]):
#         normalized_score = round(raw_score / max_rrf, 4)  # 0.0 – 1.0
#         if normalized_score < min_score:
#             continue

#         source = hit_sources[cid]
#         client_isins = [i.upper() for i in source.get("isins", [])]
#         client_tags  = [t.upper() for t in source.get("tags_of_interest", [])]

#         results.append({
#             "client_id":               cid,
#             "client_name":             source["client_name"],
#             "relevance_score":         normalized_score,
#             "matched_isins":           list(set(client_isins) & set(news_symbols)),
#             "matched_tags":            list(set(client_tags)  & set(news_tags)),
#             "matched_classifications": source.get("asset_classifications", []),
#             "classification_weights":  source.get("classification_weights", {}),
#         })

#         if len(results) >= top_k:
#             break

#     return results

# def process_news_stream(
#     news_docs: list[dict],
#     top_k: int = 5,
#     min_score: float = 0.0,
# ) -> dict[str, list[dict]]:
#     """
#     For each incoming news doc, score it against all indexed clients.
#     Returns { news_id: [matched clients with scores] }
#     News flows through — nothing is stored or deleted.
#     """
#     results = {}

#     for doc in news_docs:
#         news_id = doc.get("id", doc.get("title", "unknown"))
#         matched_clients = score_news_against_clients(doc, top_k=top_k, min_score=min_score)

#         if matched_clients:
#             results[news_id] = matched_clients
#             print(f"\nNews: {doc.get('title', '')[:60]}...")
#             for match in matched_clients:
#                 print(
#                     f"  → [{match['relevance_score']:.4f}] "
#                     f"client={match['client_name']} (id={match['client_id']}) "
#                     f"isins={match['matched_isins']} "
#                     f"tags={match['matched_tags']}"
#                 )
    
#     return results

# if __name__ == "__main__":
#     df = pd.read_csv("src/app/modules/MAS/config/portfolio.csv")
#     create_index()
#     profiles = build_all_client_profiles(df)
#     for profile in profiles.values():
#         index_client(profile)

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass, field
from collections import defaultdict
import pandas as pd
import requests
import json
import time
from pathlib import Path
from ._client import build_all_client_profiles, ClientProfile

es = Elasticsearch("http://localhost:9200", verify_certs=False)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

INDEX = "clients"
DIM = 384
CACHE_FILE = Path("src/app/modules/MAS/config/isin_to_ticker.json")


# ---------------------------------------------------------------------------
# ISIN → Ticker mapping via OpenFIGI
# ---------------------------------------------------------------------------

def build_isin_ticker_map(isins: list[str]) -> dict[str, str]:
    """
    Returns {isin: ticker} e.g. {'US5949181045': 'AAPL'}.
    Results are cached to disk — OpenFIGI is only called once.
    """
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
    batch_size = 10  # OpenFIGI max per request
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


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

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
                "ticker_symbols":         {"type": "keyword"},   # NEW
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
    """Drop and recreate — use when mapping changes (e.g. adding ticker_symbols)."""
    if es.indices.exists(index=INDEX).body:
        es.indices.delete(index=INDEX)
        print(f"Index '{INDEX}' deleted.")
    create_index()


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

def _profile_to_text(client: ClientProfile) -> str:
    return " ".join(filter(None, [
        client.query,
        " ".join(client.asset_classifications),
        " ".join(client.asset_descriptions[:20]),
        " ".join(client.currencies),
        client.mandate,
        client.client_type,
    ]))


def index_client(client: ClientProfile, isin_ticker_map: dict[str, str]) -> None:
    """Upsert a client profile including derived ticker_symbols."""
    text = _profile_to_text(client)
    embedding = embedder.encode([text], normalize_embeddings=True)[0].tolist()

    ticker_symbols = list(filter(None, [
        isin_ticker_map.get(isin) for isin in client.isins
    ]))

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
            "ticker_symbols":         ticker_symbols,            # NEW
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
          f"indexed with {len(ticker_symbols)} tickers.")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

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
    news_vec     = embedder.encode([news_text], normalize_embeddings=True)[0].tolist()
    news_tags    = [t.upper() for t in news_doc.get("tags", [])]

    # Strip exchange suffix: 'AAPL.US' → 'AAPL'
    news_tickers = [s.split(".")[0].upper() for s in news_doc.get("symbols", [])]
        # In score_news_against_clients, after news_tags is set
    print(f"[DEBUG] news_tickers: {news_tickers}")
    print(f"[DEBUG] news_tags: {news_tags}")
    # --- KNN pass ---
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

    # --- BM25 / keyword pass ---
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

    # --- RRF fusion ---
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


# ---------------------------------------------------------------------------
# Entry point — run once to build / rebuild the index
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df = pd.read_csv("src/app/modules/MAS/config/portfolio.csv")

    # Collect all ISINs across every client profile
    profiles = build_all_client_profiles(df)
    all_isins = list({isin for p in profiles.values() for isin in p.isins})
    print(f"[Setup] {len(all_isins)} unique ISINs across {len(profiles)} clients")

    # Build ISIN→ticker map (hits OpenFIGI only on first run, then uses cache)
    isin_ticker_map = build_isin_ticker_map(all_isins)

    # Recreate index to pick up the new ticker_symbols field mapping
    # Change to create_index() after first run to avoid wiping data
    create_index()

    for profile in profiles.values():
        index_client(profile, isin_ticker_map)