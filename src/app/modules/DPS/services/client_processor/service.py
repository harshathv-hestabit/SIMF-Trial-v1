import logging
from pathlib import Path

from app.modules.DPS.config.settings import settings

from .search_index import index_client_documents
from .store import upsert_client_representations
from .transform import (
    DEFAULT_PORTFOLIO_PATH,
    build_client_representations,
    load_portfolio_frame,
)


logger = logging.getLogger(__name__)


class ClientProcessorService:
    def __init__(self, portfolio_path: Path | None = None) -> None:
        configured_path = settings.CLIENT_PORTFOLIO_SOURCE_PATH.strip()
        self.portfolio_path = Path(
            portfolio_path or configured_path or DEFAULT_PORTFOLIO_PATH
        )

    async def start(self) -> None:
        logger.info("client_processor_starting portfolio_path=%s", self.portfolio_path)
        portfolio_df = load_portfolio_frame(self.portfolio_path)
        profile_documents, holdings_snapshots = build_client_representations(
            portfolio_df,
            hnw_aum_threshold_aed=settings.HNW_SEGMENT_MIN_AUM_AED,
            source_file=str(self.portfolio_path),
        )
        await upsert_client_representations(profile_documents, holdings_snapshots)
        index_client_documents(profile_documents)
        logger.info(
            "client_processor_completed portfolio_path=%s clients_processed=%s snapshots_written=%s",
            self.portfolio_path,
            len(profile_documents),
            len(holdings_snapshots),
        )
