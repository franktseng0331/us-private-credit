"""
HTML格式解析器（用于2021-2022年的BDC文件）
作为XBRL解析器的降级备选方案
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
import logging
from bs4 import BeautifulSoup
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTMLParser:
    """HTML格式解析器（用于旧版文件）"""

    def __init__(self):
        """初始化解析器"""
        # 继承XBRL解析器的列名映射
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
        解析单个BDC文件（HTML格式）

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
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()

        # 解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # 查找Schedule of Investments表格
        soi_table = self._find_soi_table(soup)
        if not soi_table:
            logger.warning(f"未找到Schedule of Investments表格: {filing_dir}")
            return []

        # 提取表格数据
        records = self._extract_table_data(soi_table, metadata)

        logger.info(f"从 {metadata['ticker']} (HTML) 提取了 {len(records)} 条记录")
        return records

    def _find_soi_table(self, soup: BeautifulSoup) -> Optional:
        """查找Schedule of Investments表格"""
        keywords = [
            'schedule of investments',
            'consolidated schedule of investments',
            'investment portfolio',
            'schedule of portfolio investments'
        ]

        # 方法1：通过标题查找
        for keyword in keywords:
            text_elements = soup.find_all(text=re.compile(keyword, re.IGNORECASE))
            for elem in text_elements:
                parent = elem.find_parent(['p', 'div', 'td', 'th'])
                if parent:
                    table = parent.find_next('table')
                    if table and self._is_valid_soi_table(table):
                        return table

        # 方法2：查找包含特定列名的表格
        tables = soup.find_all('table')
        for table in tables:
            if self._is_valid_soi_table(table):
                return table

        return None

    def _is_valid_soi_table(self, table) -> bool:
        """验证是否为有效的SOI表格"""
        # 检查表格是否包含关键列
        headers = table.find_all(['th', 'td'], limit=20)
        header_text = ' '.join([h.get_text().lower() for h in headers])

        required_keywords = ['company', 'investment', 'value', 'cost']
        matches = sum(1 for kw in required_keywords if kw in header_text)

        return matches >= 2

    def _extract_table_data(self, table, metadata: Dict) -> List[Dict]:
        """从表格中提取数据"""
        records = []

        # 提取表头
        headers = self._extract_headers(table)
        if not headers:
            logger.warning("无法提取表头")
            return []

        # 提取数据行
        rows = table.find_all('tr')

        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                continue

            # 提取单元格数据
            row_data = [self._clean_text(cell.get_text()) for cell in cells]

            # 跳过表头行和小计行
            if self._is_header_or_total_row(row_data):
                continue

            # 映射到标准字段
            record = self._map_row_to_record(headers, row_data, metadata)
            if record and record.get('borrower_name'):
                records.append(record)

        return records

    def _extract_headers(self, table) -> List[str]:
        """提取表头"""
        headers = []

        # 尝试从第一行提取
        first_row = table.find('tr')
        if first_row:
            for cell in first_row.find_all(['th', 'td']):
                headers.append(self._clean_text(cell.get_text()).lower())

        return headers

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 移除特殊字符
        text = text.strip()
        return text

    def _is_header_or_total_row(self, row_data: List[str]) -> bool:
        """判断是否为表头或小计行"""
        row_text = ' '.join(row_data).lower()
        skip_keywords = [
            'total', 'subtotal', 'total investments',
            'company', 'portfolio', 'investment type',
            'fair value', 'cost basis'
        ]
        return any(kw in row_text for kw in skip_keywords) and len(row_data) < 5

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
                'data_source': 'HTML',
                'filing_id': metadata.get('accession_number'),
                'is_amended': False,
                'parse_date': datetime.now().isoformat()
            }

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

    def _extract_quarter(self, date_str: str) -> str:
        """从日期字符串提取季度"""
        try:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            quarter = (date.month - 1) // 3 + 1
            return f"{date.year}-Q{quarter}"
        except:
            return ""


if __name__ == "__main__":
    # 测试示例
    parser = HTMLParser()
    test_dir = Path("data/raw/edgar/0001392687/2021-Q4")
    if test_dir.exists():
        records = parser.parse_filing(test_dir)
        print(f"解析了 {len(records)} 条记录")
        if records:
            print(json.dumps(records[0], indent=2))
