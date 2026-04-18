"""
HTML + N-PORT 数据合并脚本

将现有 HTML 解析结果（deal_positions.csv）与 N-PORT XML 解析结果合并，
按四字段去重后输出合并数据集供 run_cleaning.py 使用。

用法:
    python3 src/data_merger.py                         # 合并 → data/parsed/deal_positions_v2.csv
    python3 src/data_merger.py --nport-only            # 仅解析新 N-PORT 文件（跳过合并）
    python3 src/data_merger.py --stats                 # 合并后打印来源统计

去重键: [period_of_report, ticker, borrower_name, fair_value_usd_mn]
N-PORT 数据优先（drop_duplicates 保留 first，HTML 追加在后）
"""

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from nport_parser import NPortParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Deduplication key — matches on position identity across data sources
DEDUP_COLS = ["period_of_report", "ticker", "borrower_name", "fair_value_usd_mn"]

HTML_CSV = Path("data/parsed/deal_positions.csv")
NPORT_CSV = Path("data/parsed/deal_positions_nport.csv")
MERGED_CSV = Path("data/parsed/deal_positions_v2.csv")
NPORT_RAW_DIR = Path("data/raw/nport")


def parse_all_nport(output_csv: Path = NPORT_CSV) -> pd.DataFrame:
    """
    Walk data/raw/nport/<cik>/<YYYY-MM>/nport.xml, parse each file, and
    write combined results to output_csv.
    """
    parser = NPortParser()
    records = []
    xml_files = sorted(NPORT_RAW_DIR.glob("**/nport.xml"))
    logger.info(f"解析 {len(xml_files)} 个 N-PORT XML 文件...")

    for xml_path in xml_files:
        meta_path = xml_path.parent / "metadata.json"
        if not meta_path.exists():
            logger.warning(f"  缺少 metadata.json: {xml_path.parent}")
            continue
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        file_records = parser.parse_filing(xml_path, metadata)
        records.extend(file_records)
        if file_records:
            logger.info(f"  ✓ {metadata['ticker']} {metadata.get('period_of_report','?')[:7]}: {len(file_records)} 条")
        else:
            logger.warning(f"  ✗ {metadata['ticker']} {metadata.get('period_of_report','?')[:7]}: 0 条")

    if not records:
        logger.warning("N-PORT 解析结果为空，检查 data/raw/nport/ 目录是否有文件")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    logger.info(f"N-PORT 解析完成: {len(df):,} 条记录 → {output_csv}")
    return df


def merge(html_csv: Path = HTML_CSV,
          nport_csv: Path = NPORT_CSV,
          output_csv: Path = MERGED_CSV) -> pd.DataFrame:
    """
    Merge HTML and N-PORT datasets with deduplication.
    N-PORT records are placed first so they are kept on conflict.
    """
    # Load HTML data
    if not html_csv.exists():
        raise FileNotFoundError(f"HTML 数据文件不存在: {html_csv}")
    df_html = pd.read_csv(html_csv, low_memory=False)
    df_html["data_source"] = df_html.get("data_source", pd.Series(["html_parser"] * len(df_html)))
    logger.info(f"HTML 数据: {len(df_html):,} 条")

    # Load N-PORT data (parse on-the-fly if CSV not yet generated)
    if nport_csv.exists():
        df_nport = pd.read_csv(nport_csv, low_memory=False)
    else:
        logger.info("N-PORT CSV 不存在，先执行解析...")
        df_nport = parse_all_nport(nport_csv)

    if df_nport.empty:
        logger.warning("N-PORT 数据为空，输出仅含 HTML 数据")
        df_merged = df_html.copy()
        df_merged.to_csv(output_csv, index=False)
        return df_merged

    logger.info(f"N-PORT 数据: {len(df_nport):,} 条")

    # Align columns — N-PORT may have extra (lei, currency) or missing columns
    all_cols = list(dict.fromkeys(list(df_nport.columns) + list(df_html.columns)))
    df_nport = df_nport.reindex(columns=all_cols)
    df_html = df_html.reindex(columns=all_cols)

    # N-PORT first → kept on dedup conflict
    df_combined = pd.concat([df_nport, df_html], ignore_index=True)

    # Normalise key columns before dedup
    for col in ["period_of_report", "ticker", "borrower_name"]:
        if col in df_combined.columns:
            df_combined[col] = df_combined[col].astype(str).str.strip()
    if "fair_value_usd_mn" in df_combined.columns:
        df_combined["fair_value_usd_mn"] = pd.to_numeric(
            df_combined["fair_value_usd_mn"], errors="coerce"
        ).round(4)

    before = len(df_combined)
    df_merged = df_combined.drop_duplicates(subset=DEDUP_COLS, keep="first")
    removed = before - len(df_merged)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df_merged.to_csv(output_csv, index=False)
    logger.info(f"合并完成: {before:,} → {len(df_merged):,} 条（去重 {removed:,} 条）→ {output_csv}")
    return df_merged


def print_stats(df: pd.DataFrame) -> None:
    """Print source breakdown and per-BDC record counts."""
    print("\n=== 数据来源统计 ===")
    if "data_source" in df.columns:
        src = df["data_source"].value_counts()
        for s, n in src.items():
            print(f"  {s}: {n:,}")
    print(f"\n总记录: {len(df):,}  |  BDC: {df['ticker'].nunique()}  |  报告期: {df['period_of_report'].nunique()}")
    print("\n=== 各 BDC 记录数（前20） ===")
    per_bdc = df.groupby("ticker").size().sort_values(ascending=False).head(20)
    for ticker, cnt in per_bdc.items():
        src_tag = ""
        if "data_source" in df.columns:
            srcs = df[df["ticker"] == ticker]["data_source"].value_counts().to_dict()
            src_tag = "  " + "  ".join(f"{k}:{v}" for k, v in srcs.items())
        print(f"  {ticker:8s}: {cnt:5,}{src_tag}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="合并 HTML 和 N-PORT 投资数据")
    ap.add_argument("--nport-only", action="store_true", help="仅解析 N-PORT 文件，不合并")
    ap.add_argument("--stats", action="store_true", help="打印合并后的来源统计")
    ap.add_argument("--html", default=str(HTML_CSV), help="HTML 数据 CSV 路径")
    ap.add_argument("--nport-csv", default=str(NPORT_CSV), help="N-PORT 解析输出 CSV 路径")
    ap.add_argument("--output", default=str(MERGED_CSV), help="合并输出 CSV 路径")
    args = ap.parse_args()

    if args.nport_only:
        parse_all_nport(Path(args.nport_csv))
    else:
        df = merge(Path(args.html), Path(args.nport_csv), Path(args.output))
        if args.stats:
            print_stats(df)
