PORTFOLIO_REPRESENTATION_VERSION = "v1.2"

SEARCH_RELEVANCE_PROFILE = "search_relevance_profile"
CANONICAL_HOLDINGS_SNAPSHOT = "canonical_holdings_snapshot"


def build_snapshot_id(client_id: str, as_of: str) -> str:
    return f"portfolio:{client_id}:{as_of}"


def build_search_profile_document_id(snapshot_id: str) -> str:
    return f"portfolio_profile:{snapshot_id}"


def build_holdings_snapshot_document_id(snapshot_id: str) -> str:
    return f"portfolio_holdings:{snapshot_id}"


def build_holdings_container_name(base_container_name: str) -> str:
    return f"{base_container_name}_holdings"
