import re
from dataclasses import dataclass, field
from collections import defaultdict
import pandas as pd

@dataclass
class RawClientHolding:
    client_name: str
    client_no: str
    asset_type: str
    asset_subtype: str
    asset_classification: str | None
    front_type: str | None
    act_type: str | None
    ccy: str
    asset_qty: float
    market_value_aed: float
    class_1: str | None
    class_2: str | None
    dept: str | None
    client_type: str
    mandate: str
    status: int
    isin: str | None
    asset_id: str
    asset_description: str

@dataclass
class ClientProfile:
    client_id: str
    client_name: str
    client_type: str
    mandate: str
    total_aum_aed: float
    asset_types: list[str]
    asset_subtypes: list[str]
    asset_classifications: list[str]
    currencies: list[str]
    isins: list[str]
    asset_ids: list[str]
    asset_descriptions: list[str]
    classification_weights: dict[str, float]
    asset_type_weights: dict[str, float]
    ticker_symbols: list[str] = field(default_factory=list)
    query: str = field(default="")
    tags_of_interest: list[str] = field(default_factory=list)

def build_client_profile(df: pd.DataFrame) -> ClientProfile:
    assert df["Client No."].nunique() == 1, "DataFrame must contain exactly one client."

    row0 = df.iloc[0]
    client_id   = str(int(row0["Client No."]))
    client_name = str(row0["Client Name"])
    client_type = str(row0["Client Type"])
    mandate     = str(row0["Mandate"])
    total_aum   = float(df[" Market Value AED "].sum())

    asset_types           = sorted(df["Asset Type"].dropna().unique().tolist())
    asset_subtypes        = sorted(df["Asset Subtype"].dropna().unique().tolist())
    asset_classifications = sorted(df["Asset Classification"].dropna().unique().tolist())
    currencies            = sorted(df["CCY"].dropna().unique().tolist())
    isins                 = sorted(df["ISIN"].dropna().unique().tolist())
    asset_ids             = sorted(df["Asset ID"].astype(str).unique().tolist())
    asset_descriptions    = df["Asset Description"].dropna().unique().tolist()

    aum_by_classification = (
        df[df[" Market Value AED "] > 0]
        .groupby("Asset Classification")[" Market Value AED "]
        .sum()
    )
    classification_weights = {
        k: round(float(v) / total_aum, 4)
        for k, v in aum_by_classification.items()
        if pd.notna(k)
    }

    aum_by_type = (
        df[df[" Market Value AED "] > 0]
        .groupby("Asset Type")[" Market Value AED "]
        .sum()
    )
    asset_type_weights = {
        k: round(float(v) / total_aum, 4)
        for k, v in aum_by_type.items()
        if pd.notna(k)
    }

    tags_of_interest = _derive_tags(
        asset_classifications=asset_classifications,
        asset_types=asset_types,
        currencies=currencies,
    )

    query = _build_query(
        client_name=client_name,
        client_type=client_type,
        mandate=mandate,
        asset_classifications=asset_classifications,
        asset_descriptions=asset_descriptions,
        classification_weights=classification_weights,
        asset_type_weights=asset_type_weights,
        currencies=currencies,
        total_aum_aed=total_aum,
    )

    return ClientProfile(
        client_id=client_id,
        client_name=client_name,
        client_type=client_type,
        mandate=mandate,
        total_aum_aed=round(total_aum, 2),
        asset_types=asset_types,
        asset_subtypes=asset_subtypes,
        asset_classifications=asset_classifications,
        currencies=currencies,
        isins=isins,
        asset_ids=asset_ids,
        asset_descriptions=asset_descriptions,
        classification_weights=classification_weights,
        asset_type_weights=asset_type_weights,
        tags_of_interest=tags_of_interest,
        query=query,
    )

def _derive_tags(
    asset_classifications: list[str],
    asset_types: list[str],
    currencies: list[str],
) -> list[str]:
    tags = set()

    classification_tag_map = {
        "Equities":     ["EQUITY MARKETS", "STOCK MARKET", "SHARE PRICE MOVEMENT"],
        "Fixed Income": ["BOND MARKETS", "INTEREST RATE CHANGES", "CREDIT EVENTS", "YIELD CURVE"],
        "Real Estate":  ["REAL ESTATE", "REIT", "PROPERTY MARKET", "DIVIDEND PAYMENTS"],
        "Alternatives": ["ALTERNATIVE INVESTMENTS", "STRUCTURED PRODUCTS", "HEDGE FUNDS"],
        "Commodities":  ["COMMODITIES", "RAW MATERIALS", "ENERGY MARKETS", "METALS"],
        "Multi Assets": ["MULTI-ASSET", "PORTFOLIO REBALANCING", "ASSET ALLOCATION"],
    }
    for classification in asset_classifications:
        tags.update(classification_tag_map.get(classification, []))

    asset_type_tag_map = {
        "EQUITY":     ["IPO", "STOCK SPLIT", "BUYBACK", "DIVIDEND"],
        "FUNDS":      ["FUND FLOWS", "NAV", "ETF", "INDEX TRACKING"],
        "BOND":       ["BOND ISSUANCE", "DEFAULT RISK", "MATURITY", "COUPON"],
        "FIX_INCOME": ["FIXED INCOME", "DURATION RISK", "SPREAD WIDENING"],
        "REIT":       ["REAL ESTATE", "RENTAL YIELD", "PROPERTY VALUATION"],
        "ALTERNATIV": ["VOLATILITY", "DERIVATIVES", "OPTIONS"],
        "CASH":       [],
        "CFTD":       [],
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
    for ccy in currencies:
        tags.update(currency_tag_map.get(ccy, []))

    return sorted(tags)

def _build_query(
    client_name: str,
    client_type: str,
    mandate: str,
    asset_classifications: list[str],
    asset_descriptions: list[str],
    classification_weights: dict[str, float],
    asset_type_weights: dict[str, float],
    currencies: list[str],
    total_aum_aed: float,
) -> str:
    parts = []
    parts.append(
        f"{client_name} is a {client_type.lower()} client "
        f"with an {mandate.lower().replace('-', ' ')} mandate."
    )

    aum_m = total_aum_aed / 1_000_000
    if aum_m >= 1:
        parts.append(f"Total portfolio value is approximately {aum_m:.1f} million AED.")
    else:
        aum_k = total_aum_aed / 1_000
        parts.append(f"Total portfolio value is approximately {aum_k:.0f} thousand AED.")

    if classification_weights:
        meaningful = {k: v for k, v in classification_weights.items() if v >= 0.01}
        sorted_cls = sorted(meaningful.items(), key=lambda x: x[1], reverse=True)
        allocation_parts = [f"{int(w * 100)}% {cls}" for cls, w in sorted_cls]
        parts.append(f"The portfolio is allocated across: {', '.join(allocation_parts)}.")
    elif asset_type_weights:
        dominant = max(asset_type_weights, key=asset_type_weights.get)
        readable = _asset_type_label(dominant)
        parts.append(f"The portfolio is primarily held in {readable}.")

    foreign_ccys = [c for c in currencies if c != "AED"]
    if foreign_ccys:
        parts.append(
            f"The client has foreign currency exposure in {', '.join(foreign_ccys)}."
        )
    else:
        parts.append("The client holds assets in AED only.")

    real_assets = [
        d for d in asset_descriptions
        if not d.startswith("AL-")
        and not d.startswith("MX-")
        and d.strip() != "Client Fixed Term Deposit"
    ]

    if real_assets:
        options  = [d for d in real_assets if _looks_like_option(d)]
        funds    = [d for d in real_assets if _looks_like_fund(d)]
        bonds    = [d for d in real_assets if _looks_like_bond(d) and d not in funds]
        equities = [
            d for d in real_assets
            if d not in options + funds + bonds
            and _looks_like_equity(d)
        ]
        other = [
            d for d in real_assets
            if d not in options + funds + bonds + equities
        ]

        if equities:
            parts.append(f"Key equity holdings include: {', '.join(equities[:8])}.")
        if bonds:
            parts.append(f"Fixed income positions include: {', '.join(bonds[:5])}.")
        if funds:
            parts.append(f"Fund and structured vehicle positions include: {', '.join(funds[:5])}.")
        if options:
            parts.append(f"Derivatives and options positions: {', '.join(options)}.")
        if other:
            parts.append(f"Other holdings: {', '.join(other[:5])}.")
    else:
        parts.append(
            "The client holds primarily cash and fixed term deposits "
            "with no active equity or bond positions."
        )

    if classification_weights:
        dominant_cls    = max(classification_weights, key=classification_weights.get)
        dominant_weight = classification_weights[dominant_cls]

        if dominant_weight >= 0.7:
            profile_desc = f"heavily concentrated in {dominant_cls.lower()}"
        elif dominant_weight >= 0.4:
            profile_desc = f"primarily focused on {dominant_cls.lower()}"
        else:
            profile_desc = "broadly diversified across asset classes"

        # Remove the generic boilerplate — let the holdings speak for themselves
        parts.append(f"The investment profile is {profile_desc}.")

    return " ".join(parts)

_ASSET_TYPE_LABELS = {
    "CASH":       "cash",
    "CFTD":       "cash and fixed term deposits",
    "EQUITY":     "equities",
    "FIX_INCOME": "fixed income",
    "FUNDS":      "funds",
    "REIT":       "real estate investment trusts",
    "ALTERNATIV": "alternative investments",
    "BOND":       "bonds",
}

def _asset_type_label(asset_type: str) -> str:
    return _ASSET_TYPE_LABELS.get(asset_type, asset_type.lower().replace("_", " "))

_BOND_CORP_PATTERN = re.compile(
    r'\b\d+(\.\d+)?\s+\d{2}/\d{2}/\d{2,4}\s+CORP$'   # "7 08/26/28 CORP"
)
_BOND_FRACTION_PATTERN = re.compile(
    r'\b\d+\s+\d+/\d+\b'                               # "7 3/4", "9 1/4", "1 3/4"
)
_BOND_DECIMAL_COUPON = re.compile(
    r'\b\d{1,2}\.\d{1,4}\b'                            # "6.95", "5.3", "3.897"
)
_BOND_INTEGER_COUPON = re.compile(
    r'\b(BHCCN|ASTONM|SAGLEN|XRX|OB|HTZ|ARADAD)\s+\d{1,2}\s+\d{2}/\d{2}/\d{2,4}$'
)
_COMPANY_SUFFIXES = re.compile(
    r'\b(INC|AG|SE|SA|PLC|LTD|LLC|NV|BV|SPA|ASA|CORP|NYRT|GROUP)\.?$',
    re.IGNORECASE
)

_FUND_KEYWORDS = [
    "FUND", "ETF", "UCITS", "SICAV", "RAIF", "PORTFO",
    "CAPITAL", "DEBT", "BOND FUND", "RENTENSTRATEGIE",
    "WELTZINS", "PHYSICAL",                              # e.g. WISDOMTREE PHYSICAL SILVER
    "VECTORS",                                            # e.g. VANECK VECTORS GOLD MINERS
    "ISHARES", "VANECK", "WISDOMTREE", "XTRACKERS",      # known ETF issuers
    "SHS ", "SHS MAN",                                    # fund share class prefix
    "CONVERTIB",                                          # convertible bond funds
    "FIN.DEBT",                                           # GROUPAMA EURO FIN.DEBT
    "GROUPAMA",                                           # specific debt fund
]

_OPTION_KEYWORDS = ["C100", "C195", "P100", "OPTION"]


def _looks_like_option(desc: str) -> bool:
    return any(kw in desc for kw in _OPTION_KEYWORDS)


def _looks_like_fund(desc: str) -> bool:
    desc_upper = desc.upper()
    return any(kw in desc_upper for kw in _FUND_KEYWORDS)


def _looks_like_bond(desc: str) -> bool:
    """
    Bonds have:
      - Coupon fractions:  "7 3/4", "9 1/4"
      - Decimal coupons:   "6.95", "5.3", "3.897"
      - Integer coupons with date: "BHCCN 11 09/30/28", "ARADAD 8 06/24/29"
      - PERP / FLOAT keywords
      - Bond ticker with CORP suffix + date: "DAMACR 7 08/26/28 CORP"

    Explicitly NOT bonds: company names like "MICROSOFT CORP", "NVIDIA CORP"
    — these end in CORP but have no coupon/date pattern.
    """
    if _BOND_FRACTION_PATTERN.search(desc):
        return True
    if _BOND_DECIMAL_COUPON.search(desc):
        return True
    if _BOND_CORP_PATTERN.search(desc):
        return True
    if _BOND_INTEGER_COUPON.search(desc):
        return True
    if "PERP" in desc or "FLOAT" in desc:
        return True
    return False


def _looks_like_equity(desc: str) -> bool:
    """
    Equities are company names — plain words, often ending in INC/AG/SE/SA/PLC etc.
    Must not match any bond, fund, or option pattern.
    Only called after options, funds, and bonds have been ruled out.
    """
    # Must have at least 2 words
    words = desc.strip().split()
    if len(words) < 2:
        return False

    # Must start with a letter (not a number like "0 7/8")
    if words[0][0].isdigit():
        return False

    # Should end with a company suffix OR be a known all-caps company name
    if _COMPANY_SUFFIXES.search(desc):
        return True

    # Plain all-caps names without suffix also qualify (e.g. "AIRBUS SE" already caught,
    # but also standalone names like "STRABAG SE", "OTP BANK NYRT")
    return all(c.isalpha() or c in " .+&/-" for c in desc)

def build_all_client_profiles(df: pd.DataFrame) -> dict[str, ClientProfile]:
    """Build a ClientProfile for every client. Returns { client_id: ClientProfile }."""
    profiles = {}
    for client_no, group in df.groupby("Client No."):
        profile = build_client_profile(group.reset_index(drop=True))
        profiles[profile.client_id] = profile
        print(f"Built profile for {profile.client_name} (id={profile.client_id})")
    return profiles
