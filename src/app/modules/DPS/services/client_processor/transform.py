import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from app.common.portfolio_schema import (
    CANONICAL_HOLDINGS_SNAPSHOT,
    PORTFOLIO_REPRESENTATION_VERSION,
    SEARCH_RELEVANCE_PROFILE,
    build_holdings_snapshot_document_id,
    build_snapshot_id,
)


DEFAULT_PORTFOLIO_PATH = Path(__file__).resolve().parent / "portfolio.csv"
DEFAULT_ISIN_CACHE_PATH = Path(__file__).resolve().parent / "isin_to_ticker.json"
DEFAULT_HNW_AUM_THRESHOLD_AED = 10_000_000
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_BATCH_SIZE = 10
OPENFIGI_BATCH_SLEEP_SECONDS = 5
OPENFIGI_TIMEOUT_SECONDS = 30
MAX_PROFILE_ISSUER_VALUES = 12
MAX_PROFILE_PREVIEW_VALUES = 20

REAL_ASSET_EXCLUDE_PREFIXES = ("AL-", "MX-")
GENERIC_CASH_DESCRIPTIONS = {"CLIENT FIXED TERM DEPOSIT"}
ENTITY_STOPWORDS = {
    "A",
    "AND",
    "BONUS",
    "CALL",
    "CAPPED",
    "CERTIFICATE",
    "CLASS",
    "COMPOSITE",
    "CONVERTIBLE",
    "CORP",
    "DEPOSIT",
    "DUAL",
    "ENHANCED",
    "EUR",
    "FLOAT",
    "FUND",
    "FX",
    "HOLDINGS",
    "INC",
    "INDEX",
    "LIMITED",
    "NOTE",
    "NOTES",
    "OF",
    "OPTION",
    "ORD",
    "PARTICIPATION",
    "PERP",
    "PREFERRED",
    "PRODUCT",
    "PUT",
    "SA",
    "SERIES",
    "SHARES",
    "SPD",
    "SPREAD",
    "STRUCTURED",
    "THE",
    "TRUST",
    "USD",
}


@dataclass
class CanonicalHolding:
    holding_id: str
    asset_id: str
    isin: str
    ticker: str = ""
    description: str = ""
    asset_type: str = ""
    asset_subtype: str = ""
    classification: str = ""
    front_type: str = ""
    act_type: str = ""
    currency: str = ""
    market_value_aed: float = 0.0
    market_value_local: float = 0.0
    quantity: float = 0.0
    portfolio_weight: float = 0.0
    issuer_name: str = ""
    issuer_normalized: str = ""
    sector: str = ""
    region: str = ""
    country: str = ""
    underlying_ticker: str = ""
    derivative_metadata: dict[str, Any] | None = None
    bond_metadata: dict[str, Any] | None = None
    source_row_hash: str = ""


@dataclass
class ClientPortfolio:
    client_id: str
    client_name: str
    client_type: str
    client_segment: str
    client_segment_reason: str
    mandate: str
    total_aum_aed: float
    snapshot_id: str
    as_of: str
    asset_types: list[str]
    asset_subtypes: list[str]
    asset_classifications: list[str]
    currencies: list[str]
    asset_class_weights: dict[str, float]
    asset_type_weights: dict[str, float]
    broad_tags_of_interest: list[str] = field(default_factory=list)
    compact_summary_text: str = ""
    holdings: list[CanonicalHolding] = field(default_factory=list)


def load_portfolio_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Portfolio CSV not found at {path}")
    print("Portfolios loaded")
    return pd.read_csv(path)


def build_client_representations(
    portfolio_df: pd.DataFrame,
    cache_path: Path = DEFAULT_ISIN_CACHE_PATH,
    hnw_aum_threshold_aed: float = DEFAULT_HNW_AUM_THRESHOLD_AED,
    *,
    as_of: str | None = None,
    source_file: str = "",
) -> tuple[list[dict], list[dict]]:
    effective_as_of = as_of or _utcnow_iso()
    portfolios = build_all_client_portfolios(
        portfolio_df,
        hnw_aum_threshold_aed=hnw_aum_threshold_aed,
        as_of=effective_as_of,
    )
    all_isins = sorted(
        {
            holding.isin
            for portfolio in portfolios.values()
            for holding in portfolio.holdings
            if holding.isin
        }
    )
    isin_ticker_map = build_isin_ticker_map(all_isins, cache_path=cache_path)
    attach_ticker_symbols(portfolios, isin_ticker_map)
    print("Client Portfolio Processing Complete!")
    return (
        [
            client_profile_to_document(
                portfolio,
                source_file=source_file,
                generated_at=effective_as_of,
            )
            for portfolio in portfolios.values()
        ],
        [
            canonical_holdings_snapshot_to_document(
                portfolio,
                source_file=source_file,
                generated_at=effective_as_of,
            )
            for portfolio in portfolios.values()
        ],
    )


def build_client_documents(
    portfolio_df: pd.DataFrame,
    cache_path: Path = DEFAULT_ISIN_CACHE_PATH,
    hnw_aum_threshold_aed: float = DEFAULT_HNW_AUM_THRESHOLD_AED,
) -> list[dict]:
    profiles, _ = build_client_representations(
        portfolio_df,
        cache_path=cache_path,
        hnw_aum_threshold_aed=hnw_aum_threshold_aed,
    )
    return profiles


def build_isin_ticker_map(
    isins: list[str],
    cache_path: Path = DEFAULT_ISIN_CACHE_PATH,
) -> dict[str, str]:
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        missing = [isin for isin in isins if isin not in cached]
        if not missing:
            return cached
        isins = missing
    else:
        cached = {}

    if not isins:
        return cached

    mapping: dict[str, str] = {}
    for index in range(0, len(isins), OPENFIGI_BATCH_SIZE):
        batch = isins[index:index + OPENFIGI_BATCH_SIZE]
        jobs = [{"idType": "ID_ISIN", "idValue": isin} for isin in batch]
        response = requests.post(
            OPENFIGI_URL,
            json=jobs,
            headers={"Content-Type": "application/json"},
            timeout=OPENFIGI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        for isin, result in zip(batch, response.json()):
            for hit in result.get("data", []):
                ticker = hit.get("ticker")
                if ticker:
                    mapping[isin] = _normalize_ticker(ticker)
                    break
        if index + OPENFIGI_BATCH_SIZE < len(isins):
            time.sleep(OPENFIGI_BATCH_SLEEP_SECONDS)

    merged = {**cached, **mapping}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(merged, indent=2))
    print("ISIN mappings completed")
    return merged


def attach_ticker_symbols(
    portfolios: dict[str, ClientPortfolio],
    isin_ticker_map: dict[str, str],
) -> None:
    for portfolio in portfolios.values():
        for holding in portfolio.holdings:
            mapped_ticker = _normalize_ticker(isin_ticker_map.get(holding.isin, ""))
            if mapped_ticker:
                holding.ticker = mapped_ticker
                if not holding.underlying_ticker and holding.asset_type not in {
                    "CASH",
                    "CFTD",
                }:
                    holding.underlying_ticker = mapped_ticker


def client_profile_to_document(
    portfolio: ClientPortfolio,
    *,
    source_file: str,
    generated_at: str,
) -> dict:
    major_tickers = _rank_distinct_holding_values(
        portfolio.holdings,
        value_getter=lambda holding: holding.ticker or holding.underlying_ticker,
        limit=None,
    )
    major_issuers = _rank_distinct_holding_values(
        portfolio.holdings,
        value_getter=lambda holding: holding.issuer_name,
        limit=MAX_PROFILE_ISSUER_VALUES,
    )
    top_descriptions = _top_holding_values(
        portfolio.holdings,
        value_getter=lambda holding: holding.description,
        limit=MAX_PROFILE_PREVIEW_VALUES,
    )
    top_isins = _top_holding_values(
        portfolio.holdings,
        value_getter=lambda holding: holding.isin,
        limit=MAX_PROFILE_PREVIEW_VALUES,
    )
    top_asset_ids = _top_holding_values(
        portfolio.holdings,
        value_getter=lambda holding: holding.asset_id,
        limit=MAX_PROFILE_PREVIEW_VALUES,
    )

    return {
        "id": portfolio.client_id,
        "representation_type": SEARCH_RELEVANCE_PROFILE,
        "representation_version": PORTFOLIO_REPRESENTATION_VERSION,
        "client_id": portfolio.client_id,
        "client_name": portfolio.client_name,
        "client_type": portfolio.client_type,
        "client_segment": portfolio.client_segment,
        "client_segment_reason": portfolio.client_segment_reason,
        "mandate": portfolio.mandate,
        "total_aum_aed": portfolio.total_aum_aed,
        "snapshot_id": portfolio.snapshot_id,
        "as_of": portfolio.as_of,
        "generated_at": generated_at,
        "source_file": source_file,
        "holdings_count": len(portfolio.holdings),
        "asset_types": portfolio.asset_types,
        "asset_subtypes": portfolio.asset_subtypes,
        "asset_classifications": portfolio.asset_classifications,
        "currencies": portfolio.currencies,
        "asset_class_weights": portfolio.asset_class_weights,
        "asset_type_weights": portfolio.asset_type_weights,
        "broad_tags_of_interest": portfolio.broad_tags_of_interest,
        "major_tickers": major_tickers,
        "major_issuers": major_issuers,
        "major_sectors": [],
        "major_asset_descriptions": top_descriptions,
        "compact_summary_text": portfolio.compact_summary_text,
        "classification_weights": portfolio.asset_class_weights,
        "ticker_symbols": major_tickers,
        "tags_of_interest": portfolio.broad_tags_of_interest,
        "query": portfolio.compact_summary_text,
        "asset_descriptions": top_descriptions,
        "isins": top_isins,
        "asset_ids": top_asset_ids,
    }


def canonical_holdings_snapshot_to_document(
    portfolio: ClientPortfolio,
    *,
    source_file: str,
    generated_at: str,
) -> dict:
    return {
        "id": build_holdings_snapshot_document_id(portfolio.snapshot_id),
        "representation_type": CANONICAL_HOLDINGS_SNAPSHOT,
        "representation_version": PORTFOLIO_REPRESENTATION_VERSION,
        "client_id": portfolio.client_id,
        "client_name": portfolio.client_name,
        "client_type": portfolio.client_type,
        "client_segment": portfolio.client_segment,
        "client_segment_reason": portfolio.client_segment_reason,
        "mandate": portfolio.mandate,
        "total_aum_aed": portfolio.total_aum_aed,
        "snapshot_id": portfolio.snapshot_id,
        "as_of": portfolio.as_of,
        "generated_at": generated_at,
        "source_file": source_file,
        "holdings_count": len(portfolio.holdings),
        "holdings": [canonical_holding_to_document(holding) for holding in portfolio.holdings],
    }


def canonical_holding_to_document(holding: CanonicalHolding) -> dict:
    return {
        "holding_id": holding.holding_id,
        "asset_id": _none_if_empty(holding.asset_id),
        "isin": _none_if_empty(holding.isin),
        "ticker": _none_if_empty(holding.ticker),
        "description": _none_if_empty(holding.description),
        "asset_type": _none_if_empty(holding.asset_type),
        "asset_subtype": _none_if_empty(holding.asset_subtype),
        "classification": _none_if_empty(holding.classification),
        "front_type": _none_if_empty(holding.front_type),
        "act_type": _none_if_empty(holding.act_type),
        "currency": _none_if_empty(holding.currency),
        "market_value_aed": holding.market_value_aed,
        "market_value_local": holding.market_value_local,
        "quantity": holding.quantity,
        "portfolio_weight": holding.portfolio_weight,
        "issuer_name": _none_if_empty(holding.issuer_name),
        "issuer_normalized": _none_if_empty(holding.issuer_normalized),
        "sector": _none_if_empty(holding.sector),
        "region": _none_if_empty(holding.region),
        "country": _none_if_empty(holding.country),
        "underlying_ticker": _none_if_empty(holding.underlying_ticker),
        "derivative_metadata": holding.derivative_metadata,
        "bond_metadata": holding.bond_metadata,
        "source_row_hash": holding.source_row_hash,
    }


def build_client_portfolio(
    df: pd.DataFrame,
    *,
    hnw_aum_threshold_aed: float = DEFAULT_HNW_AUM_THRESHOLD_AED,
    as_of: str,
) -> ClientPortfolio:
    assert df["Client No."].nunique() == 1, "DataFrame must contain exactly one client."

    row0 = df.iloc[0]
    client_id = _clean_client_id(row0["Client No."])
    client_name = _clean_string(row0["Client Name"])
    client_type = _clean_string(row0["Client Type"])
    mandate = _clean_string(row0["Mandate"])
    total_aum = round(float(df[" Market Value AED "].fillna(0).sum()), 2)
    client_segment, client_segment_reason = _derive_client_segment(
        total_aum_aed=total_aum,
        hnw_aum_threshold_aed=hnw_aum_threshold_aed,
    )

    asset_types = _sorted_unique(df["Asset Type"])
    asset_subtypes = _sorted_unique(df["Asset Subtype"])
    asset_classifications = _sorted_unique(df["Asset Classification"])
    currencies = _sorted_unique(df["CCY"])
    snapshot_id = build_snapshot_id(client_id, as_of)

    asset_class_weights = _build_weight_map(
        df=df,
        group_field="Asset Classification",
        total_aum=total_aum,
    )
    asset_type_weights = _build_weight_map(
        df=df,
        group_field="Asset Type",
        total_aum=total_aum,
    )
    asset_descriptions = [
        _clean_string(value)
        for value in df["Asset Description"].tolist()
        if _clean_string(value)
    ]

    holdings = _build_canonical_holdings(
        df,
        client_id=client_id,
        total_aum_aed=total_aum,
    )
    broad_tags_of_interest = _derive_tags(
        asset_classifications=asset_classifications,
        asset_types=asset_types,
        currencies=currencies,
    )
    compact_summary_text = _build_compact_summary_text(
        client_name=client_name,
        client_type=client_type,
        mandate=mandate,
        asset_classifications=asset_classifications,
        asset_descriptions=asset_descriptions,
        asset_class_weights=asset_class_weights,
        asset_type_weights=asset_type_weights,
        currencies=currencies,
        total_aum_aed=total_aum,
    )
    print(f"Client Portfolio {client_id} built")
    return ClientPortfolio(
        client_id=client_id,
        client_name=client_name,
        client_type=client_type,
        client_segment=client_segment,
        client_segment_reason=client_segment_reason,
        mandate=mandate,
        total_aum_aed=total_aum,
        snapshot_id=snapshot_id,
        as_of=as_of,
        asset_types=asset_types,
        asset_subtypes=asset_subtypes,
        asset_classifications=asset_classifications,
        currencies=currencies,
        asset_class_weights=asset_class_weights,
        asset_type_weights=asset_type_weights,
        broad_tags_of_interest=broad_tags_of_interest,
        compact_summary_text=compact_summary_text,
        holdings=holdings,
    )


def build_all_client_portfolios(
    df: pd.DataFrame,
    *,
    hnw_aum_threshold_aed: float = DEFAULT_HNW_AUM_THRESHOLD_AED,
    as_of: str,
) -> dict[str, ClientPortfolio]:
    portfolios = {}
    for _, group in df.groupby("Client No."):
        portfolio = build_client_portfolio(
            group.reset_index(drop=True),
            hnw_aum_threshold_aed=hnw_aum_threshold_aed,
            as_of=as_of,
        )
        portfolios[portfolio.client_id] = portfolio
    return portfolios


def _derive_client_segment(
    *,
    total_aum_aed: float,
    hnw_aum_threshold_aed: float,
) -> tuple[str, str]:
    threshold = max(float(hnw_aum_threshold_aed), 0.0)
    if total_aum_aed >= threshold:
        return "hnw", f"total_aum_aed>={threshold:.2f}"
    return "retail", f"total_aum_aed<{threshold:.2f}"


def _build_canonical_holdings(
    df: pd.DataFrame,
    *,
    client_id: str,
    total_aum_aed: float,
) -> list[CanonicalHolding]:
    holdings: list[CanonicalHolding] = []
    for row_index, row in df.reset_index(drop=True).iterrows():
        description = _clean_string(row.get("Asset Description"))
        asset_id = _clean_string(row.get("Asset ID"))
        asset_type = _clean_string(row.get("Asset Type"))
        asset_subtype = _clean_string(row.get("Asset Subtype"))
        market_value_aed = round(_safe_float(row.get(" Market Value AED ")), 6)
        portfolio_weight = round(
            (market_value_aed / total_aum_aed) if total_aum_aed else 0.0,
            6,
        )
        issuer_name = _derive_issuer_name(description)
        holding = CanonicalHolding(
            holding_id=f"{client_id}:{asset_id or 'row'}:{row_index}",
            asset_id=asset_id,
            isin=_clean_string(row.get("ISIN")),
            description=description,
            asset_type=asset_type,
            asset_subtype=asset_subtype,
            classification=_clean_string(row.get("Asset Classification")),
            front_type=_clean_string(row.get("FrontType")),
            act_type=_clean_string(row.get("ACTType")),
            currency=_clean_string(row.get("CCY")),
            market_value_aed=market_value_aed,
            market_value_local=round(_safe_float(row.get("Market Value")), 6),
            quantity=round(_safe_float(row.get("Asset Qty")), 6),
            portfolio_weight=portfolio_weight,
            issuer_name=issuer_name,
            issuer_normalized=_normalize_keyword(issuer_name),
            underlying_ticker=_infer_underlying_ticker(
                description,
                asset_type=asset_type,
                asset_subtype=asset_subtype,
            ),
            derivative_metadata=_build_derivative_metadata(
                description=description,
                asset_type=asset_type,
                asset_subtype=asset_subtype,
            ),
            bond_metadata=_build_bond_metadata(description),
            source_row_hash=_build_source_row_hash(row.to_dict()),
        )
        holdings.append(holding)
    holdings.sort(
        key=lambda holding: (
            -holding.market_value_aed,
            holding.asset_id,
            holding.holding_id,
        )
    )
    return holdings


def _build_weight_map(
    *,
    df: pd.DataFrame,
    group_field: str,
    total_aum: float,
) -> dict[str, float]:
    grouped = (
        df[df[" Market Value AED "] > 0]
        .groupby(group_field)[" Market Value AED "]
        .sum()
    )
    return {
        key: round(float(value) / total_aum, 4)
        for key, value in grouped.items()
        if pd.notna(key) and _clean_string(key) and total_aum > 0
    }


def _sorted_unique(series: pd.Series) -> list[str]:
    return sorted(
        {
            _clean_string(value)
            for value in series.dropna().tolist()
            if _clean_string(value)
        }
    )


def _derive_tags(
    asset_classifications: list[str],
    asset_types: list[str],
    currencies: list[str],
) -> list[str]:
    tags = set()

    classification_tag_map = {
        "Equities": ["EQUITY MARKETS", "STOCK MARKET", "SHARE PRICE MOVEMENT"],
        "Fixed Income": ["BOND MARKETS", "INTEREST RATE CHANGES", "CREDIT EVENTS", "YIELD CURVE"],
        "Real Estate": ["REAL ESTATE", "REIT", "PROPERTY MARKET", "DIVIDEND PAYMENTS"],
        "Alternatives": ["ALTERNATIVE INVESTMENTS", "STRUCTURED PRODUCTS", "HEDGE FUNDS"],
        "Commodities": ["COMMODITIES", "RAW MATERIALS", "ENERGY MARKETS", "METALS"],
        "Multi Assets": ["MULTI-ASSET", "PORTFOLIO REBALANCING", "ASSET ALLOCATION"],
    }
    for classification in asset_classifications:
        tags.update(classification_tag_map.get(classification, []))

    asset_type_tag_map = {
        "EQUITY": ["IPO", "STOCK SPLIT", "BUYBACK", "DIVIDEND"],
        "FUNDS": ["FUND FLOWS", "NAV", "ETF", "INDEX TRACKING"],
        "BOND": ["BOND ISSUANCE", "DEFAULT RISK", "MATURITY", "COUPON"],
        "FIX_INCOME": ["FIXED INCOME", "DURATION RISK", "SPREAD WIDENING"],
        "REIT": ["REAL ESTATE", "RENTAL YIELD", "PROPERTY VALUATION"],
        "ALTERNATIV": ["VOLATILITY", "DERIVATIVES", "OPTIONS"],
        "CASH": [],
        "CFTD": [],
    }
    for asset_type in asset_types:
        tags.update(asset_type_tag_map.get(asset_type, []))

    currency_tag_map = {
        "EUR": ["EURO ZONE", "ECB POLICY", "EUROPEAN MARKETS"],
        "USD": ["US MARKETS", "FED POLICY", "DOLLAR STRENGTH"],
        "GBP": ["UK MARKETS", "BOE POLICY"],
        "JPY": ["JAPAN MARKETS", "BOJ POLICY", "YEN"],
        "CHF": ["SWISS MARKETS", "SNB POLICY"],
        "AUD": ["AUSTRALIA MARKETS", "RBA POLICY"],
        "SGD": ["SINGAPORE MARKETS", "MAS POLICY"],
        "CNY": ["CHINA MARKETS", "PBOC POLICY", "YUAN"],
        "HKD": ["HONG KONG MARKETS"],
    }
    for currency in currencies:
        tags.update(currency_tag_map.get(currency, []))

    return sorted(tags)


def _build_compact_summary_text(
    client_name: str,
    client_type: str,
    mandate: str,
    asset_classifications: list[str],
    asset_descriptions: list[str],
    asset_class_weights: dict[str, float],
    asset_type_weights: dict[str, float],
    currencies: list[str],
    total_aum_aed: float,
) -> str:
    parts = [
        f"{client_name} is a {client_type.lower()} client with an {mandate.lower().replace('-', ' ')} mandate."
    ]

    aum_m = total_aum_aed / 1_000_000
    if aum_m >= 1:
        parts.append(f"Total portfolio value is approximately {aum_m:.1f} million AED.")
    else:
        aum_k = total_aum_aed / 1_000
        parts.append(f"Total portfolio value is approximately {aum_k:.0f} thousand AED.")

    if asset_class_weights:
        meaningful = {key: value for key, value in asset_class_weights.items() if value >= 0.01}
        sorted_cls = sorted(meaningful.items(), key=lambda item: item[1], reverse=True)
        allocation_parts = [f"{int(weight * 100)}% {classification}" for classification, weight in sorted_cls]
        if allocation_parts:
            parts.append(f"The portfolio is allocated across: {', '.join(allocation_parts)}.")
    elif asset_type_weights:
        dominant = max(asset_type_weights, key=asset_type_weights.get)
        parts.append(f"The portfolio is primarily held in {_asset_type_label(dominant)}.")

    foreign_ccys = [currency for currency in currencies if currency != "AED"]
    if foreign_ccys:
        parts.append(f"The client has foreign currency exposure in {', '.join(foreign_ccys)}.")
    else:
        parts.append("The client holds assets in AED only.")

    real_assets = [description for description in asset_descriptions if _is_real_asset_description(description)]
    if real_assets:
        options = [description for description in real_assets if _looks_like_option(description)]
        funds = [description for description in real_assets if _looks_like_fund(description)]
        bonds = [description for description in real_assets if _looks_like_bond(description) and description not in funds]
        equities = [
            description
            for description in real_assets
            if description not in options + funds + bonds and _looks_like_equity(description)
        ]
        other = [
            description
            for description in real_assets
            if description not in options + funds + bonds + equities
        ]

        if equities:
            parts.append(f"Key equity holdings include: {', '.join(equities[:8])}.")
        if bonds:
            parts.append(f"Fixed income positions include: {', '.join(bonds[:5])}.")
        if funds:
            parts.append(f"Fund and structured vehicle positions include: {', '.join(funds[:5])}.")
        if options:
            parts.append(f"Derivatives and options positions: {', '.join(options[:5])}.")
        if other:
            parts.append(f"Other holdings: {', '.join(other[:5])}.")
    else:
        parts.append(
            "The client holds primarily cash and fixed term deposits with no active equity or bond positions."
        )

    if asset_class_weights:
        dominant_classification = max(asset_class_weights, key=asset_class_weights.get)
        dominant_weight = asset_class_weights[dominant_classification]
        if dominant_weight >= 0.7:
            profile_description = f"heavily concentrated in {dominant_classification.lower()}"
        elif dominant_weight >= 0.4:
            profile_description = f"primarily focused on {dominant_classification.lower()}"
        else:
            profile_description = "broadly diversified across asset classes"
        parts.append(f"The investment profile is {profile_description}.")

    return " ".join(parts)


_ASSET_TYPE_LABELS = {
    "CASH": "cash",
    "CFTD": "cash and fixed term deposits",
    "EQUITY": "equities",
    "FIX_INCOME": "fixed income",
    "FUNDS": "funds",
    "REIT": "real estate investment trusts",
    "ALTERNATIV": "alternative investments",
    "BOND": "bonds",
}


def _asset_type_label(asset_type: str) -> str:
    return _ASSET_TYPE_LABELS.get(asset_type, asset_type.lower().replace("_", " "))


_BOND_CORP_PATTERN = re.compile(r"\b\d+(\.\d+)?\s+\d{2}/\d{2}/\d{2,4}\s+CORP$")
_BOND_FRACTION_PATTERN = re.compile(r"\b\d+\s+\d+/\d+\b")
_BOND_DECIMAL_COUPON = re.compile(r"\b\d{1,2}\.\d{1,4}\b")
_BOND_INTEGER_COUPON = re.compile(r"\b(BHCCN|ASTONM|SAGLEN|XRX|OB|HTZ|ARADAD)\s+\d{1,2}\s+\d{2}/\d{2}/\d{2,4}$")
_COMPANY_SUFFIXES = re.compile(r"\b(INC|AG|SE|SA|PLC|LTD|LLC|NV|BV|SPA|ASA|CORP|NYRT|GROUP)\.?$", re.IGNORECASE)
_FUND_KEYWORDS = [
    "FUND",
    "ETF",
    "UCITS",
    "SICAV",
    "RAIF",
    "PORTFO",
    "CAPITAL",
    "DEBT",
    "BOND FUND",
    "RENTENSTRATEGIE",
    "WELTZINS",
    "PHYSICAL",
    "VECTORS",
    "ISHARES",
    "VANECK",
    "WISDOMTREE",
    "XTRACKERS",
    "SHS ",
    "SHS MAN",
    "CONVERTIB",
    "FIN.DEBT",
    "GROUPAMA",
]
_OPTION_KEYWORDS = ["C100", "C195", "P100", "OPTION"]
_SYMBOL_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")


def _looks_like_option(description: str) -> bool:
    description_upper = description.upper()
    return any(keyword in description_upper for keyword in _OPTION_KEYWORDS)


def _looks_like_fund(description: str) -> bool:
    description_upper = description.upper()
    return any(keyword in description_upper for keyword in _FUND_KEYWORDS)


def _looks_like_bond(description: str) -> bool:
    if _BOND_FRACTION_PATTERN.search(description):
        return True
    if _BOND_DECIMAL_COUPON.search(description):
        return True
    if _BOND_CORP_PATTERN.search(description):
        return True
    if _BOND_INTEGER_COUPON.search(description):
        return True
    if "PERP" in description or "FLOAT" in description:
        return True
    return False


def _looks_like_equity(description: str) -> bool:
    words = description.strip().split()
    if len(words) < 2:
        return False
    if words[0][0].isdigit():
        return False
    if _COMPANY_SUFFIXES.search(description):
        return True
    return all(character.isalpha() or character in " .+&/-" for character in description)


def _is_real_asset_description(description: str) -> bool:
    normalized = description.strip().upper()
    if not normalized:
        return False
    if normalized.startswith(REAL_ASSET_EXCLUDE_PREFIXES):
        return False
    if normalized in GENERIC_CASH_DESCRIPTIONS:
        return False
    return True


def _derive_issuer_name(description: str) -> str:
    if not _is_real_asset_description(description):
        return ""
    tokens = []
    for token in re.findall(r"[A-Z0-9][A-Z0-9.&/-]*", description.upper()):
        cleaned = token.strip(".")
        if not cleaned or cleaned in ENTITY_STOPWORDS:
            continue
        if cleaned.isdigit():
            continue
        if re.fullmatch(r"\d{2}/\d{2}/\d{2,4}", cleaned):
            continue
        tokens.append(cleaned)
        if len(tokens) >= 4:
            break
    return " ".join(tokens)


def _infer_underlying_ticker(
    description: str,
    *,
    asset_type: str,
    asset_subtype: str,
) -> str:
    if asset_type in {"CASH", "CFTD"} or not _is_real_asset_description(description):
        return ""
    if asset_subtype == "STRUCTURED_PRODUCT":
        candidates = _extract_symbol_candidates(description)
        return candidates[-1] if candidates else ""
    return ""


def _extract_symbol_candidates(description: str) -> list[str]:
    candidates = []
    for token in _SYMBOL_PATTERN.findall(description.upper()):
        if token in ENTITY_STOPWORDS:
            continue
        if token.isdigit():
            continue
        candidates.append(token)
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _build_derivative_metadata(
    *,
    description: str,
    asset_type: str,
    asset_subtype: str,
) -> dict[str, Any] | None:
    if asset_subtype == "STRUCTURED_PRODUCT":
        return {"instrument_family": "structured_product"}
    if _looks_like_option(description):
        return {"instrument_family": "option"}
    if asset_type == "ALTERNATIV":
        return {"instrument_family": "alternative"}
    return None


def _build_bond_metadata(description: str) -> dict[str, Any] | None:
    if _looks_like_bond(description):
        return {"instrument_family": "bond"}
    return None


def _build_source_row_hash(row: dict[str, Any]) -> str:
    values = [
        _clean_string(row.get(field))
        for field in [
            "Client No.",
            "Asset ID",
            "ISIN",
            "Asset Description",
            "Asset Qty",
            " Market Value AED ",
            "Market Value",
            "CCY",
        ]
    ]
    return sha1("|".join(values).encode("utf-8")).hexdigest()


def _rank_distinct_holding_values(
    holdings: list[CanonicalHolding],
    *,
    value_getter,
    limit: int | None,
) -> list[str]:
    totals: dict[str, float] = {}
    labels: dict[str, str] = {}
    for holding in holdings:
        value = _clean_string(value_getter(holding))
        if not value:
            continue
        normalized = _normalize_keyword(value)
        totals[normalized] = totals.get(normalized, 0.0) + max(holding.market_value_aed, 0.0)
        labels.setdefault(normalized, value)
    ranked = sorted(totals.items(), key=lambda item: (-item[1], labels[item[0]]))
    if limit is None:
        return [labels[key] for key, _ in ranked]
    return [labels[key] for key, _ in ranked[:limit]]


def _top_holding_values(
    holdings: list[CanonicalHolding],
    *,
    value_getter,
    limit: int,
) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for holding in holdings:
        value = _clean_string(value_getter(holding))
        normalized = _normalize_keyword(value)
        if not value or normalized in seen:
            continue
        selected.append(value)
        seen.add(normalized)
        if len(selected) >= limit:
            break
    return selected


def _clean_client_id(value: object | None) -> str:
    text = _clean_string(value)
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


def _safe_float(value: object | None) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _clean_string(value: object | None) -> str:
    return str(value or "").strip()


def _normalize_keyword(value: object | None) -> str:
    text = _clean_string(value).upper()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text)


def _normalize_ticker(value: object | None) -> str:
    text = _normalize_keyword(value)
    if not text:
        return ""
    return text.split(".")[0]


def _none_if_empty(value: object | None) -> Any:
    text = _clean_string(value)
    return text or None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
