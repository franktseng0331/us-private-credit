"""
SEC EDGAR BDC数据下载器
使用edgartools库下载BDC的10-Q和10-K文件
"""
import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Clear proxy environment variables to avoid httpx proxy errors
for key in list(os.environ.keys()):
    if 'proxy' in key.lower():
        del os.environ[key]

try:
    from edgar import Company, set_identity
except ImportError:
    print("请先安装edgartools: pip install edgartools>=2.0.0")
    raise

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BDCCollector:
    """BDC数据采集器"""

    def __init__(self, config_path: str = "config/bdc_ciks.json",
                 raw_data_dir: str = "data/raw/edgar",
                 user_agent: str = "YourCompany admin@email.com"):
        """
        初始化采集器

        Args:
            config_path: BDC CIK配置文件路径
            raw_data_dir: 原始数据存储目录
            user_agent: SEC要求的User-Agent（格式：公司名 邮箱）
        """
        self.config_path = config_path
        self.raw_data_dir = Path(raw_data_dir)
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)

        # 设置SEC身份标识（必需）
        set_identity(user_agent)

        # 加载BDC列表
        self.bdcs = self._load_bdc_config()

        # 速率限制：10请求/秒
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.last_request_time = 0

        # 失败下载记录
        self.failed_downloads = []

    def _load_bdc_config(self) -> Dict:
        """加载BDC配置文件"""
        with open(self.config_path, 'r') as f:
            return json.load(f)

    def _rate_limit(self):
        """实现速率限制（10请求/秒）"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def download_filing(self, cik: str, ticker: str,
                       filing_type: str = "10-Q",
                       start_date: str = "2021-01-01",
                       end_date: str = "2025-12-31",
                       max_retries: int = 3) -> List[Dict]:
        """
        下载单个BDC的历史申报文件

        Args:
            cik: SEC CIK编号
            ticker: 股票代码
            filing_type: 文件类型（10-Q或10-K）
            start_date: 开始日期
            end_date: 结束日期
            max_retries: 最大重试次数

        Returns:
            下载成功的文件信息列表
        """
        self._rate_limit()
        downloaded_files = []

        for attempt in range(max_retries):
            try:
                logger.info(f"下载 {ticker} ({cik}) 的 {filing_type} 文件 ({start_date} 到 {end_date})...")

                # 使用edgartools获取公司信息
                company = Company(cik)

                # 获取指定时间范围内的所有文件
                filings = company.get_filings(form=filing_type)

                # 获取指定时间范围内的所有文件
                filings = company.get_filings(form=filing_type)

                if not filings:
                    logger.warning(f"{ticker} 没有找到 {filing_type} 文件")
                    return downloaded_files

                # 遍历所有文件，筛选时间范围内的
                for filing in filings:
                    filing_date = filing.filing_date

                    # 检查日期范围
                    if filing_date < datetime.strptime(start_date, "%Y-%m-%d").date():
                        continue
                    if filing_date > datetime.strptime(end_date, "%Y-%m-%d").date():
                        continue

                    # 创建保存目录
                    quarter = self._get_quarter(filing_date)
                    save_dir = self.raw_data_dir / cik / quarter

                    # 检查是否已下载
                    metadata_path = save_dir / "metadata.json"
                    if metadata_path.exists():
                        logger.info(f"  跳过已下载: {ticker} {quarter}")
                        continue

                    save_dir.mkdir(parents=True, exist_ok=True)

                    # 保存文件元数据
                    metadata = {
                        "ticker": ticker,
                        "cik": cik,
                        "filing_type": filing_type,
                        "filing_date": str(filing_date),
                        "accession_number": filing.accession_no,
                        "period_of_report": str(filing.period_of_report) if hasattr(filing, 'period_of_report') else None,
                        "download_time": datetime.now().isoformat()
                    }

                    metadata_path = save_dir / "metadata.json"
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)

                    # 保存原始HTML/XML
                    html_path = save_dir / f"{filing.accession_no}.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(filing.html())

                    logger.info(f"  ✓ 下载成功: {ticker} {quarter}")

                    downloaded_files.append({
                        "save_path": str(save_dir),
                        "filing_date": str(filing_date),
                        "period_of_report": str(filing.period_of_report) if hasattr(filing, 'period_of_report') else None,
                        "accession_number": filing.accession_no
                    })

                    # 速率限制
                    self._rate_limit()

                return downloaded_files

            except Exception as e:
                logger.error(f"下载失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(30)  # 等待30秒后重试
                else:
                    self.failed_downloads.append({
                        "ticker": ticker,
                        "cik": cik,
                        "filing_type": filing_type,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    return downloaded_files

    def _get_quarter(self, date) -> str:
        """将日期转换为季度标签（如2024-Q3）"""
        year = date.year
        month = date.month
        quarter = (month - 1) // 3 + 1
        return f"{year}-Q{quarter}"

    def download_all_bdcs(self, filing_types: List[str] = ["10-Q"],
                         start_date: str = "2021-01-01",
                         end_date: str = "2025-12-31"):
        """
        批量下载所有BDC的历史文件

        Args:
            filing_types: 要下载的文件类型列表（默认只下载10-Q）
            start_date: 开始日期
            end_date: 结束日期
        """
        logger.info(f"开始下载 {len(self.bdcs)} 个BDC的文件 ({start_date} 到 {end_date})...")

        for ticker, bdc_info in self.bdcs.items():
            cik = bdc_info["cik"] if isinstance(bdc_info, dict) else bdc_info
            logger.info(f"\n处理 {ticker} (CIK: {cik})...")

            for filing_type in filing_types:
                result = self.download_filing(
                    cik=cik,
                    ticker=ticker,
                    filing_type=filing_type,
                    start_date=start_date,
                    end_date=end_date
                )

                if result:
                    logger.info(f"  {ticker} {filing_type}: 下载了 {len(result)} 个文件")
                else:
                    logger.warning(f"  {ticker} {filing_type}: 下载失败或无文件")

        # 保存失败记录
        if self.failed_downloads:
            failed_path = Path("data/parsed/failed_downloads.json")
            failed_path.parent.mkdir(parents=True, exist_ok=True)
            with open(failed_path, 'w') as f:
                json.dump(self.failed_downloads, f, indent=2)
            logger.warning(f"有 {len(self.failed_downloads)} 个文件下载失败，详见 {failed_path}")

        logger.info("下载完成！")


    def download_nport_filings(self, cik: str, ticker: str,
                               start_date: str = "2021-01-01",
                               end_date: str = "2026-03-31",
                               max_retries: int = 3) -> List[Dict]:
        """
        下载 N-PORT-P XML 文件到 data/raw/nport/<cik>/<YYYY-MM>/.

        N-PORT-P 是 SEC 要求投资公司每月提交的结构化 XML 报告（非 HTML），
        每月提交（vs 10-Q 每季度），覆盖密度 3 倍。

        Args:
            cik: SEC CIK 编号
            ticker: 股票代码
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            max_retries: 最大重试次数

        Returns:
            成功下载的文件信息列表 [{xml_path, filing_date, period_of_report, ...}]
        """
        nport_dir = self.raw_data_dir.parent / "nport"
        downloaded = []

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                company = Company(cik)
                filings = company.get_filings(form="N-PORT-P")

                if not filings:
                    logger.warning(f"{ticker} 没有找到 N-PORT-P 文件")
                    return downloaded

                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

                for filing in filings:
                    filing_date = filing.filing_date

                    if filing_date < start_dt or filing_date > end_dt:
                        continue

                    period = getattr(filing, "period_of_report", None)
                    period_str = str(period)[:7] if period else str(filing_date)[:7]  # YYYY-MM

                    save_dir = nport_dir / cik / period_str
                    metadata_path = save_dir / "metadata.json"

                    if metadata_path.exists():
                        logger.info(f"  跳过已下载: {ticker} {period_str}")
                        downloaded.append({"xml_path": str(save_dir / "nport.xml"),
                                           "filing_date": str(filing_date),
                                           "period_of_report": str(period),
                                           "accession_number": filing.accession_no,
                                           "ticker": ticker, "cik": cik})
                        continue

                    save_dir.mkdir(parents=True, exist_ok=True)

                    # N-PORT primary document is XML
                    try:
                        xml_content = filing.primary_document.content
                        if xml_content is None:
                            logger.warning(f"  {ticker} {period_str}: primary document 内容为空")
                            continue
                    except Exception as e:
                        logger.warning(f"  {ticker} {period_str}: 获取 XML 失败: {e}")
                        continue

                    xml_path = save_dir / "nport.xml"
                    if isinstance(xml_content, str):
                        xml_path.write_text(xml_content, encoding="utf-8")
                    else:
                        xml_path.write_bytes(xml_content)

                    metadata = {
                        "ticker": ticker,
                        "cik": cik,
                        "filing_type": "N-PORT-P",
                        "filing_date": str(filing_date),
                        "accession_number": filing.accession_no,
                        "period_of_report": str(period),
                        "download_time": datetime.now().isoformat(),
                    }
                    metadata_path.write_text(json.dumps(metadata, indent=2))

                    logger.info(f"  ✓ N-PORT 下载成功: {ticker} {period_str}")
                    downloaded.append({"xml_path": str(xml_path),
                                       "filing_date": str(filing_date),
                                       "period_of_report": str(period),
                                       "accession_number": filing.accession_no,
                                       "ticker": ticker, "cik": cik})
                    self._rate_limit()

                return downloaded

            except Exception as e:
                logger.error(f"N-PORT 下载失败 {ticker} (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(30)
                else:
                    self.failed_downloads.append({
                        "ticker": ticker, "cik": cik,
                        "filing_type": "N-PORT-P", "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    })
        return downloaded

    def download_all_nport(self, start_date: str = "2021-01-01",
                           end_date: str = "2026-03-31"):
        """批量下载所有 BDC 的 N-PORT-P 文件。"""
        logger.info(f"开始下载 {len(self.bdcs)} 个 BDC 的 N-PORT-P 文件 ({start_date} 到 {end_date})...")

        for ticker, bdc_info in self.bdcs.items():
            cik = bdc_info["cik"] if isinstance(bdc_info, dict) else bdc_info
            logger.info(f"\n处理 {ticker} (CIK: {cik})...")
            result = self.download_nport_filings(cik=cik, ticker=ticker,
                                                  start_date=start_date, end_date=end_date)
            logger.info(f"  {ticker}: 下载/已有 {len(result)} 个 N-PORT 文件")

        if self.failed_downloads:
            failed_path = Path("data/parsed/failed_downloads_nport.json")
            failed_path.parent.mkdir(parents=True, exist_ok=True)
            failed_path.write_text(json.dumps(self.failed_downloads, indent=2))
            logger.warning(f"有 {len(self.failed_downloads)} 个文件下载失败，详见 {failed_path}")

        logger.info("N-PORT 下载完成！")


if __name__ == "__main__":
    # 使用示例
    collector = BDCCollector(user_agent="PrivateCreditResearch research@example.com")

    # 测试：下载单个BDC
    collector.download_filing("0001392687", "ARCC", "10-Q")

    # 批量下载所有BDC
    # collector.download_all_bdcs()

