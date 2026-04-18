"""
N-PORT XML 解析器
解析 SEC N-PORT-P (Monthly Portfolio Reports) XML 文件，提取投资持仓明细。

N-PORT-P 是 SEC 要求投资公司每月提交的结构化 XML 报告，包含完整投资组合明细。
BDC 每月提交（vs 10-Q 每季度），数据密度 3 倍于 HTML 方案。

字段名与 simple_parser.py 输出保持一致，新增 data_source='nport_xml'。
"""

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# N-PORT XML namespace (SEC uses this for all N-PORT submissions)
_NS = "http://www.sec.gov/edgar/nport"

# SEC assetCat → investment_type_std mapping
ASSET_CAT_MAP = {
    "DBT": "Senior Secured",      # Debt security (refined by titleOfIssue below)
    "EC": "Common Equity",
    "STIV": "Common Equity",      # Short-term investment vehicle (treated as equity)
    "ABS": "Structured Finance / CLO",
    "OPT": "Warrant / Option",
    "FUT": "Warrant / Option",
    "FWD": "Warrant / Option",
    "SWP": "Structured Finance / CLO",  # swaps
    "OTH": "Other",
}

# titleOfIssue keyword → investment_type_std (checked when assetCat == 'DBT')
_TITLE_MAP = [
    (["first lien", "senior secured", "term loan a", "term loan b", "tl-"], "Senior Secured"),
    (["second lien", "2nd lien", "junior secured"], "Second Lien"),
    (["subordinated", "mezzanine", "junior", "unsecured note", "high yield", "senior note"], "Subordinated Debt"),
    (["revolving", "revolver", "delayed draw", "ddtl"], "Revolver"),
    (["convertible"], "Subordinated Debt"),
    (["preferred", "pref. stock"], "Preferred Equity"),
    (["warrant"], "Warrant / Option"),
    (["clo", "abs", "structured"], "Structured Finance / CLO"),
]


def _tag(local: str) -> str:
    return f"{{{_NS}}}{local}"


def _text(element, local: str) -> Optional[str]:
    child = element.find(_tag(local))
    return child.text.strip() if child is not None and child.text else None


def _float(element, local: str) -> Optional[float]:
    val = _text(element, local)
    if val is None:
        return None
    try:
        return float(val.replace(",", ""))
    except ValueError:
        return None


def _classify_debt(title: str) -> str:
    if not title:
        return "Senior Secured"
    lower = title.lower()
    for keywords, inv_type in _TITLE_MAP:
        if any(kw in lower for kw in keywords):
            return inv_type
    return "Senior Secured"


def _classify_investment_type(asset_cat: Optional[str], title: Optional[str]) -> str:
    if not asset_cat:
        return "Other"
    if asset_cat == "DBT":
        return _classify_debt(title or "")
    return ASSET_CAT_MAP.get(asset_cat, "Other")


class NPortParser:
    """Parse a single N-PORT XML file and return a list of investment records."""

    def parse_filing(self, xml_path: Path, metadata: dict) -> list:
        """
        Parse one N-PORT XML file.

        Args:
            xml_path: Path to the .xml file
            metadata: dict with keys ticker, cik, filing_date, period_of_report, accession_number

        Returns:
            List of dicts with fields matching simple_parser.py output + data_source
        """
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError as e:
            logger.warning(f"XML parse error in {xml_path}: {e}")
            return []

        root = tree.getroot()
        records = []

        # Handle both namespaced and plain XML (some older N-PORTs lack namespace)
        for inv in root.iter(_tag("invstOrSec")):
            record = self._extract(inv, metadata)
            if record:
                records.append(record)

        # Fallback: try without namespace
        if not records:
            for inv in root.iter("invstOrSec"):
                record = self._extract_plain(inv, metadata)
                if record:
                    records.append(record)

        return records

    # ------------------------------------------------------------------
    # Extraction helpers (namespaced)
    # ------------------------------------------------------------------

    def _extract(self, inv: ET.Element, meta: dict) -> Optional[dict]:
        name = _text(inv, "name")
        if not name:
            return None

        val_usd = _float(inv, "valUSD")
        # Allow val_usd == 0 (unfunded commitments)
        if val_usd is None:
            return None

        balance = _float(inv, "balance")
        title = _text(inv, "titleOfIssue")
        asset_cat = _text(inv, "assetCat")
        lei = _text(inv, "lei")
        cur_cd = _text(inv, "curCd") or "USD"

        # Debt-specific fields
        debt = inv.find(_tag("debtSec"))
        maturity_dt = None
        coupon_kind = None
        annualized_rte = None
        if debt is not None:
            maturity_dt = _text(debt, "maturityDt")
            coupon_kind = _text(debt, "couponKind")
            annualized_rte = _text(debt, "annualizedRte")

        inv_type = _classify_investment_type(asset_cat, title)

        return {
            "ticker": meta["ticker"],
            "cik": meta["cik"],
            "filing_date": meta["filing_date"],
            "period_of_report": meta["period_of_report"],
            "accession_number": meta.get("accession_number", ""),
            "borrower_name": name,
            "lei": lei,
            "investment_type_raw": title or "",
            "investment_type_std": inv_type,
            "industry_raw": "",
            "fair_value_usd_mn": val_usd / 1e6,
            "position_size_usd_mn": (balance / 1e6) if balance is not None else val_usd / 1e6,
            "cost_basis_usd_mn": None,
            "maturity_date_raw": maturity_dt or "",
            "interest_rate_raw": _build_rate_str(coupon_kind, annualized_rte),
            "currency": cur_cd,
            "data_source": "nport_xml",
        }

    def _extract_plain(self, inv: ET.Element, meta: dict) -> Optional[dict]:
        """Fallback for N-PORT files without XML namespace declarations."""

        def txt(tag):
            el = inv.find(tag)
            return el.text.strip() if el is not None and el.text else None

        def flt(tag):
            v = txt(tag)
            try:
                return float(v.replace(",", "")) if v else None
            except ValueError:
                return None

        name = txt("name")
        if not name:
            return None
        val_usd = flt("valUSD")
        if val_usd is None:
            return None

        debt = inv.find("debtSec")
        maturity_dt = txt("debtSec/maturityDt") if debt is not None else None
        coupon_kind = txt("debtSec/couponKind") if debt is not None else None
        annualized_rte = txt("debtSec/annualizedRte") if debt is not None else None

        inv_type = _classify_investment_type(txt("assetCat"), txt("titleOfIssue"))
        balance = flt("balance")

        return {
            "ticker": meta["ticker"],
            "cik": meta["cik"],
            "filing_date": meta["filing_date"],
            "period_of_report": meta["period_of_report"],
            "accession_number": meta.get("accession_number", ""),
            "borrower_name": name,
            "lei": txt("lei"),
            "investment_type_raw": txt("titleOfIssue") or "",
            "investment_type_std": inv_type,
            "industry_raw": "",
            "fair_value_usd_mn": val_usd / 1e6,
            "position_size_usd_mn": (balance / 1e6) if balance is not None else val_usd / 1e6,
            "cost_basis_usd_mn": None,
            "maturity_date_raw": maturity_dt or "",
            "interest_rate_raw": _build_rate_str(coupon_kind, annualized_rte),
            "currency": txt("curCd") or "USD",
            "data_source": "nport_xml",
        }


def _build_rate_str(coupon_kind: Optional[str], annualized_rte: Optional[str]) -> str:
    """Convert N-PORT rate fields into a rate string compatible with data_cleaner step6."""
    if not annualized_rte:
        return ""
    try:
        rate = float(annualized_rte)
    except ValueError:
        return ""
    if coupon_kind == "FLT":
        # Floating: we don't know spread vs base, store as SOFR+X as best guess
        # step6 will extract spread_bps from this format
        return f"SOFR + {rate:.2f}%"
    elif coupon_kind == "FXD":
        return f"{rate:.2f}% Fixed"
    else:
        return f"{rate:.2f}%"
