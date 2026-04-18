"""
run_nport.py — N-PORT 数据采集、解析、合并一体化脚本

用法:
    python3 run_nport.py --download          # 下载所有 BDC 的 N-PORT XML 文件
    python3 run_nport.py --parse             # 解析已下载的 XML → deal_positions_nport.csv
    python3 run_nport.py --merge             # 合并 HTML + N-PORT → deal_positions_v2.csv
    python3 run_nport.py --all               # 依次执行 download → parse → merge
    python3 run_nport.py --ticker ARCC --download   # 只处理指定 BDC

合并完成后运行清洗:
    python3 run_cleaning.py --input data/parsed/deal_positions_v2.csv
"""

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add src/ to import path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bdc_collector import BDCCollector
from data_merger import merge, parse_all_nport, print_stats

CONFIG_PATH = "config/bdc_ciks.json"
USER_AGENT = "PrivateCreditResearch research@example.com"
START_DATE = "2021-01-01"
END_DATE = "2026-03-31"


def cmd_download(ticker_filter=None):
    collector = BDCCollector(config_path=CONFIG_PATH, user_agent=USER_AGENT)
    bdcs = collector.bdcs

    if ticker_filter:
        bdcs = {k: v for k, v in bdcs.items() if k.upper() == ticker_filter.upper()}
        if not bdcs:
            logger.error(f"Ticker '{ticker_filter}' 不在 BDC 列表中")
            return

    total = 0
    for ticker, info in bdcs.items():
        cik = info["cik"] if isinstance(info, dict) else info
        logger.info(f"\n下载 {ticker} (CIK: {cik}) N-PORT 文件...")
        result = collector.download_nport_filings(
            cik=cik, ticker=ticker, start_date=START_DATE, end_date=END_DATE
        )
        logger.info(f"  {ticker}: {len(result)} 个文件")
        total += len(result)

    logger.info(f"\nN-PORT 下载完成，共 {total} 个文件")


def cmd_parse():
    df = parse_all_nport()
    if not df.empty:
        logger.info(f"解析完成: {len(df):,} 条记录")
    else:
        logger.warning("解析结果为空")


def cmd_merge(stats=False):
    df = merge()
    if stats and not df.empty:
        print_stats(df)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="N-PORT 数据流水线")
    ap.add_argument("--download", action="store_true", help="下载 N-PORT XML 文件")
    ap.add_argument("--parse", action="store_true", help="解析 N-PORT XML → CSV")
    ap.add_argument("--merge", action="store_true", help="合并 HTML + N-PORT 数据")
    ap.add_argument("--all", action="store_true", help="依次执行 download → parse → merge")
    ap.add_argument("--ticker", type=str, default=None, help="只处理指定 BDC（如 ARCC）")
    ap.add_argument("--stats", action="store_true", help="合并后打印来源统计")
    args = ap.parse_args()

    if not any([args.download, args.parse, args.merge, args.all]):
        ap.print_help()
        sys.exit(0)

    if args.all or args.download:
        cmd_download(args.ticker)

    if args.all or args.parse:
        cmd_parse()

    if args.all or args.merge:
        cmd_merge(stats=args.stats)
