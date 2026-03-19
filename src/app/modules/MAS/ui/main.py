import sys
from pathlib import Path

import streamlit as st
from azure.cosmos import CosmosClient


SRC_ROOT = Path(__file__).resolve().parents[4]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.modules.MAS.config.settings import settings


st.set_page_config(page_title="SMIF Clients", layout="wide")
st.title("SMIF Clients")


@st.cache_resource
def get_cosmos_client() -> CosmosClient:
    return CosmosClient(
        url=settings.COSMOS_URL,
        credential=settings.COSMOS_KEY,
        connection_verify=False,
        enable_endpoint_discovery=False,
        connection_timeout=5,
    )


def get_container(container_name: str):
    client = get_cosmos_client()
    return (
        client.get_database_client(settings.COSMOS_DB)
        .get_container_client(container_name)
    )


@st.cache_data(ttl=30)
def load_clients() -> list[dict]:
    container = get_container(settings.CLIENT_PORTFOLIO_CONTAINER)
    query = """
    SELECT c.client_id, c.client_name
    FROM c
    ORDER BY c.client_name
    """
    items = list(
        container.query_items(
            query=query,
            enable_cross_partition_query=True,
        )
    )
    deduped = {}
    for item in items:
        client_id = item.get("client_id")
        if client_id:
            deduped[client_id] = {
                "client_id": client_id,
                "client_name": item.get("client_name", client_id),
            }
    return list(deduped.values())


@st.cache_data(ttl=30)
def load_insights(client_id: str) -> list[dict]:
    container = get_container(settings.INSIGHTS_CONTAINER)
    query = """
    SELECT c.id, c.client_id, c.insight, c.verification_score,
           c.news_title, c.tickers, c.status, c.timestamp
    FROM c
    WHERE c.client_id = @client_id
    ORDER BY c.timestamp DESC
    """
    return list(
        container.query_items(
            query=query,
            parameters=[{"name": "@client_id", "value": client_id}],
            partition_key=client_id,
        )
    )


def render_insight_card(insight: dict) -> None:
    title = insight.get("news_title") or "Untitled Insight"
    score = insight.get("verification_score")
    status = insight.get("status", "unknown")
    timestamp = insight.get("timestamp", "unknown")
    tickers = insight.get("tickers") or []

    with st.container(border=True):
        st.subheader(title)
        cols = st.columns(3)
        cols[0].caption(f"Status: {status}")
        cols[1].caption(f"Verification Score: {score}")
        cols[2].caption(f"Timestamp: {timestamp}")

        if tickers:
            st.caption("Tickers: " + ", ".join(tickers))

        st.write(insight.get("insight", "No insight text available."))


try:
    clients = load_clients()
except Exception as exc:
    st.error(f"Failed to load clients from Cosmos DB: {exc}")
    st.stop()

if not clients:
    st.info("No client profiles are available yet.")
    st.stop()


client_options = {
    f"{client['client_name']} ({client['client_id']})": client["client_id"]
    for client in clients
}

selected_label = st.selectbox("Select Client", list(client_options.keys()))
selected_client_id = client_options[selected_label]


try:
    insights = load_insights(selected_client_id)
except Exception as exc:
    st.error(f"Failed to load insights for client {selected_client_id}: {exc}")
    st.stop()


if not insights:
    st.info(f"No insights found for client {selected_client_id}.")
else:
    st.write(f"Showing {len(insights)} insight(s) for client `{selected_client_id}`.")
    for insight in insights:
        render_insight_card(insight)
