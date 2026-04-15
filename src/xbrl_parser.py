"""
XBRL格式解析器（用于2022年后的BDC文件）
从Schedule of Investments表格中提取贷款数据
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class XBRLParser:
    """XBRL格式解析器"""

    def __init__(self):
        """初始化解析器"""
        # 常见的列名映射（不同BDC可能使用不同的列名）
        self.column_mappings = {
            'borrower': ['company', 'portfolio company', 'investment', 'borrower'],
            'industry': ['industry', 'sector', 'business'],
            'investment_type': ['investment type', 'type', 'instrument'],
            'interest_rate': ['interest rate', 'rate', 'coupon', 'yield'],
            'maturity': ['maturity', 'maturity date', 'due date'],
            'principal': ['principal', 'par value', 'par amount'],
            'cost': ['cost', 'amortized cost', 'cost basis'],
            'fair_value': ['fair value', 'value', 'market value']
        }

    def parse_filing(self, filing_dir) -> List[Dict]:
        """
        解析单个BDC文件

        Args:
            filing_dir: 文件目录路径（字符串或Path对象）

        Returns:
            解析后的交易记录列表
        """
        # 确保是Path对象
        filing_dir = Path(filing_dir)

        # 读取元数据
        metadata_path = filing_dir / "metadata.json"
        if not metadata_path.exists():
            logger.error(f"元数据文件不存在: {metadata_path}")
            return []

        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        # 读取HTML文件
        html_files = list(filing_dir.glob("*.html"))
        if not html_files:
            logger.error(f"HTML文件不存在: {filing_dir}")
            return []

        html_path = html_files[0]
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 解析HTML
        soup = BeautifulSoup(html_content, 'lxml')

        # 查找Schedule of Investments表格
        soi_table = self._find_soi_table(soup)
        if not soi_table:
            logger.warning(f"未找到Schedule of Investments表格: {filing_dir}")
            return []

        # 提取表格数据
        records = self._extract_table_data(soi_table, metadata)

        logger.info(f"从 {metadata['ticker']} 提取了 {len(records)} 条记录")
        return records

    def _find_soi_table(self, soup: BeautifulSoup) -> Optional:
        """查找Schedule of Investments表格"""
        # 查找包含"Schedule of Investments"的标题
        keywords = [
            'schedule of investments',
            'consolidated schedule of investments',
            'investment portfolio'
        ]

        for keyword in keywords:
            # 查找标题
            headers = soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'div'])
            for header in headers:
                if header.text and keyword in header.text.lower():
                    # 找到标题后，查找后续的表格
                    table = header.find_next('table')
                    if table:
                        return table

        # 如果没找到，尝试查找包含特定列名的表格
        tables = soup.find_all('table')
        for table in tables:
            headers = table.find_all(['th', 'td'])
            header_text = ' '.join([h.text.lower() for h in headers[:10]])
            if 'portfolio company' in header_text or 'investment' in header_text:
                return table

        return None

    def _extract_table_data(self, table, metadata: Dict) -> List[Dict]:
        """从表格中提取数据"""
        records = []

        # 提取表头
        headers = []
        header_row = table.find('tr')
        if header_row:
            for th in header_row.find_all(['th', 'td']):
                headers.append(th.text.strip().lower())

        # 提取数据行
        rows = table.find_all('tr')[1:]  # 跳过表头

        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:  # 跳过空行或小计行
                continue

            # 提取单元格数据
            row_data = [cell.text.strip() for cell in cells]

            # 跳过小计行和总计行
            if any(keyword in ' '.join(row_data).lower()
                   for keyword in ['total', 'subtotal', 'total investments']):
                continue

            # 映射到标准字段
            record = self._map_row_to_record(headers, row_data, metadata)
            if record and record.get('borrower_name'):
                records.append(record)

        return records

    def _map_row_to_record(self, headers: List[str],
                           row_data: List[str],
                           metadata: Dict) -> Optional[Dict]:
        """将表格行映射到标准记录格式"""
        try:
            record = {
                # BDC信息
                'cik': metadata['cik'],
                'bdc_name': metadata.get('ticker', ''),
                'ticker': metadata['ticker'],
                'filing_type': metadata['filing_type'],
                'filing_date': metadata['filing_date'],
                'period_of_report': metadata.get('period_of_report'),
                'quarter': self._extract_quarter(metadata['filing_date']),

                # 从表格提取的字段
                'borrower_name': self._find_value(headers, row_data, 'borrower'),
                'industry': self._find_value(headers, row_data, 'industry'),
                'investment_type': self._find_value(headers, row_data, 'investment_type'),
                'interest_rate_raw': self._find_value(headers, row_data, 'interest_rate'),
                'maturity_raw': self._find_value(headers, row_data, 'maturity'),
                'position_size_usd_mn': self._parse_number(
                    self._find_value(headers, row_data, 'principal')
                ),
                'cost_basis_usd_mn': self._parse_number(
                    self._find_value(headers, row_data, 'cost')
                ),
                'fair_value_usd_mn': self._parse_number(
                    self._find_value(headers, row_data, 'fair_value')
                ),

                # 元数据
                'data_source': 'XBRL',
                'filing_id': metadata.get('accession_number'),
                'is_amended': False,
                'parse_date': metadata.get('download_time')
            }

            # 解析利率字段
            rate_info = self._parse_interest_rate(record['interest_rate_raw'])
            record.update(rate_info)

            return record

        except Exception as e:
            logger.error(f"映射记录失败: {e}")
            return None

    def _find_value(self, headers: List[str], row_data: List[str], field_type: str) -> str:
        """根据列名查找对应的值"""
        possible_names = self.column_mappings.get(field_type, [])

        for i, header in enumerate(headers):
            if any(name in header for name in possible_names):
                if i < len(row_data):
                    return row_data[i]

        return ""

    def _parse_number(self, value: str) -> Optional[float]:
        """解析数字（处理千位分隔符、括号等）"""
        if not value:
            return None

        try:
            # 移除逗号、美元符号、括号
            cleaned = re.sub(r'[,$()]', '', value)
            # 处理负数（括号表示）
            if '(' in value:
                cleaned = '-' + cleaned
            return float(cleaned) / 1000  # 转换为百万
        except:
            return None

    def _parse_interest_rate(self, rate_str: str) -> Dict:
        """解析利率字符串"""
        if not rate_str:
            return {
                'base_rate': None,
                'spread_raw': None,
                'is_pik': False
            }

        rate_str_lower = rate_str.lower()

        # 检测PIK
        is_pik = 'pik' in rate_str_lower

        # 提取基准利率
        base_rate = None
        if 'sofr' in rate_str_lower:
            base_rate = 'SOFR'
        elif 'libor' in rate_str_lower or ' l ' in rate_str_lower or rate_str_lower.startswith('l '):
            base_rate = 'LIBOR'
        elif 'prime' in rate_str_lower:
            base_rate = 'Prime'
        elif '%' in rate_str and '+' not in rate_str:
            base_rate = 'Fixed'

        # 提取利差
        spread_match = re.search(r'\+\s*([\d.]+)', rate_str)
        spread_raw = spread_match.group(1) if spread_match else None

        return {
            'base_rate': base_rate,
            'spread_raw': spread_raw,
            'is_pik': is_pik
        }

    def _extract_quarter(self, date_str: str) -> str:
        """从日期字符串提取季度"""
        from datetime import datetime
        try:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            quarter = (date.month - 1) // 3 + 1
            return f"{date.year}-Q{quarter}"
        except:
            return ""


if __name__ == "__main__":
    # 测试解析器
    parser = XBRLParser()
    # 示例：解析单个文件
    # records = parser.parse_filing(Path("data/raw/edgar/0001392687/2024-Q3"))
    # print(f"提取了 {len(records)} 条记录")
