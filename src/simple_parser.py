"""
简化的投资数据解析器
专门用于解析BDC的Schedule of Investments表格
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleParser:
    """简化的投资数据解析器"""

    def parse_filing(self, filing_dir) -> List[Dict]:
        """
        解析BDC文件中的投资数据

        Args:
            filing_dir: 文件目录路径

        Returns:
            投资记录列表
        """
        filing_dir = Path(filing_dir)

        # 读取元数据
        metadata_path = filing_dir / "metadata.json"
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        # 读取HTML文件
        html_files = list(filing_dir.glob("*.html"))
        if not html_files:
            logger.error(f"未找到HTML文件: {filing_dir}")
            return []

        html_path = html_files[0]
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')

        # 查找所有投资表格
        investment_tables = []
        for i, table in enumerate(tables):
            table_text = table.get_text().lower()

            # 识别投资表格的特征（放宽条件以匹配FSIC格式）
            if ('portfolio company' in table_text and 'fair value' in table_text):
                investment_tables.append(table)
            elif (('borrower' in table_text or 'company' in table_text) and
                ('fair value' in table_text or 'principal' in table_text) and
                ('coupon' in table_text or 'interest rate' in table_text or 'spread' in table_text)):
                investment_tables.append(table)

        logger.info(f"找到 {len(investment_tables)} 个投资表格")

        # 从所有表格中提取数据
        all_records = []
        for table in investment_tables:
            records = self._extract_from_table(table, metadata)
            all_records.extend(records)

        logger.info(f"从 {metadata['ticker']} 提取了 {len(all_records)} 条记录")
        return all_records

    def _extract_from_table(self, table, metadata: Dict) -> List[Dict]:
        """从单个表格中提取投资记录"""
        records = []
        rows = table.find_all('tr')

        if len(rows) < 2:
            return records

        # 查找表头行（包含"Company"或"Investment"的行）
        header_row_idx = 0
        header_cells = []
        for i, row in enumerate(rows[:5]):
            row_text = row.get_text().lower()
            if 'company' in row_text and ('investment' in row_text or 'coupon' in row_text):
                header_row_idx = i
                header_cells = [cell.get_text().strip().lower() for cell in row.find_all(['td', 'th'])]
                break

        # 解析数据行
        current_company = None
        current_industry = None

        # 要排除的非投资行关键词
        exclude_keywords = [
            'total', 'subtotal', 'interest receivable', 'fee payable',
            'payable', 'receivable', 'total investments', 'total portfolio',
            'percentage', 'as of', 'unaudited', 'see notes'
        ]

        for row in rows[header_row_idx + 1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                continue

            cell_texts = [cell.get_text().strip() for cell in cells]

            # 跳过空行
            if not any(cell_texts):
                continue

            # 跳过汇总行和会计科目行
            row_text_lower = ' '.join(cell_texts).lower()
            if any(keyword in row_text_lower for keyword in exclude_keywords):
                continue

            # 第一列通常是公司名或投资类型
            first_col = cell_texts[0] if cell_texts[0] else None

            # 如果第一列有内容且不是数字，可能是新公司
            if first_col and not self._is_numeric(first_col) and len(first_col) > 3:
                # 排除汇总关键词
                if not any(kw in first_col.lower() for kw in ['total', 'subtotal', 'sum', 'aggregate']):
                    # 位置逻辑：第一列非数字且长度>3，视为公司名
                    current_company = first_col
                    # 第二列可能是行业描述
                    if len(cell_texts) > 1 and cell_texts[1] and not self._is_numeric(cell_texts[1]):
                        current_industry = cell_texts[1]

            # 查找投资类型（loan, equity, etc）
            investment_type = None
            for cell in cell_texts[:4]:
                if cell and ('loan' in cell.lower() or 'equity' in cell.lower() or
                           'stock' in cell.lower() or 'units' in cell.lower() or
                           'interest' in cell.lower() or 'warrant' in cell.lower() or
                           'note' in cell.lower()):
                    investment_type = cell
                    break

            # 必须有投资类型才算有效记录
            if not investment_type:
                continue

            # --- 提取利率相关字段 ---
            interest_rate_raw = None
            base_rate = None
            spread_raw = None
            is_pik = False

            for cell in cell_texts:
                if cell and '%' in cell and self._is_numeric(cell.replace('%', '').strip()):
                    interest_rate_raw = cell
                    break
                # SOFR/LIBOR + spread format
                if cell and re.search(r'(SOFR|LIBOR|Prime|L\s*\+|S\s*\+)', cell, re.IGNORECASE):
                    interest_rate_raw = cell
                    break

            # 如果没找到带%的单元格，寻找包含利率信息的单元格
            if not interest_rate_raw:
                for cell in cell_texts:
                    if cell and re.search(r'\d+\.?\d*\s*%|bps|basis', cell, re.IGNORECASE):
                        interest_rate_raw = cell
                        break

            if interest_rate_raw:
                base_rate = self._extract_base_rate(interest_rate_raw)
                spread_raw = self._extract_spread(interest_rate_raw)
                is_pik = self._detect_pik(interest_rate_raw, row_text_lower)

            # --- 提取到期日 ---
            maturity_raw = self._extract_maturity(cell_texts)

            # --- 提取优先级 ---
            seniority = self._extract_seniority(investment_type, row_text_lower)

            # --- 提取本金/成本/公允价值 ---
            numeric_values = []
            for cell in cell_texts:
                if cell and self._is_numeric(cell):
                    try:
                        val = float(cell.replace(',', '').replace('(', '-').replace(')', ''))
                        numeric_values.append((cell, val))
                    except:
                        pass

            # 公允价值（最后几列中的数字）
            fair_value = None
            for cell in reversed(cell_texts[-5:]):
                if cell and self._is_numeric(cell):
                    try:
                        val = float(cell.replace(',', ''))
                        if val > 0.1:
                            fair_value = cell
                            break
                    except:
                        pass

            # 本金/面值（通常是倒数第2-3个较大数字）
            position_size_raw = None
            cost_basis_raw = None
            if len(numeric_values) >= 2:
                # 假设顺序：...principal, cost, fair_value
                # 最后一个是fair_value，倒数第二个是cost，倒数第三个是principal
                if len(numeric_values) >= 3:
                    position_size_raw = numeric_values[-3][0]
                    cost_basis_raw = numeric_values[-2][0]
                elif len(numeric_values) >= 2:
                    cost_basis_raw = numeric_values[-2][0]

            # filing_id from metadata
            filing_id = metadata.get('accession_number', '')
            # is_amended: accession number ends with /A or contains amendment indicator
            is_amended = bool(filing_id and ('/A' in filing_id or filing_id.endswith('-A')))

            # 如果找到了关键信息，创建记录
            if current_company and investment_type and fair_value:
                # 提取季度信息
                quarter = self._extract_quarter(metadata.get('period_of_report', ''))

                record = {
                    # BDC信息
                    'cik': metadata['cik'],
                    'bdc_name': metadata.get('ticker', ''),
                    'ticker': metadata.get('ticker', ''),
                    'filing_type': metadata.get('filing_type', '10-Q'),
                    'filing_date': metadata['filing_date'],
                    'period_of_report': metadata.get('period_of_report', ''),
                    'quarter': quarter,
                    # 借款人信息
                    'borrower_name': current_company,
                    'industry': current_industry or '',
                    # 贷款条款
                    'investment_type': investment_type,
                    'seniority': seniority,
                    'is_pik': is_pik,
                    'interest_rate_raw': interest_rate_raw or '',
                    'base_rate': base_rate or '',
                    'spread_raw': spread_raw or '',
                    'maturity_raw': maturity_raw or '',
                    # 财务数据
                    'position_size_usd_mn': self._parse_fair_value(position_size_raw),
                    'cost_basis_usd_mn': self._parse_fair_value(cost_basis_raw),
                    'fair_value_raw': fair_value,
                    'fair_value_usd_mn': self._parse_fair_value(fair_value),
                    # 元数据
                    'data_source': 'HTML',
                    'filing_id': filing_id,
                    'is_amended': is_amended,
                    'raw_row': ' | '.join(cell_texts[:10])
                }
                records.append(record)

        return records

    def _extract_base_rate(self, rate_text: str) -> str:
        """从利率文本中提取基准利率类型"""
        if not rate_text:
            return ''
        text_upper = rate_text.upper()
        if 'SOFR' in text_upper:
            return 'SOFR'
        elif 'LIBOR' in text_upper:
            return 'LIBOR'
        elif 'PRIME' in text_upper:
            return 'Prime'
        elif re.search(r'\bL\s*\+', rate_text):
            return 'LIBOR'
        elif re.search(r'\bS\s*\+', rate_text):
            return 'SOFR'
        elif '%' in rate_text and not re.search(r'(SOFR|LIBOR|Prime|\+)', rate_text, re.IGNORECASE):
            return 'Fixed'
        return ''

    def _extract_spread(self, rate_text: str) -> str:
        """从利率文本中提取利差"""
        if not rate_text:
            return ''
        # Pattern: "SOFR + 550", "L + 5.50%", "SOFR+550bps"
        match = re.search(r'\+\s*(\d+\.?\d*)\s*(bps|%|basis)?', rate_text, re.IGNORECASE)
        if match:
            val = match.group(1)
            unit = match.group(2) or ''
            return f"{val}{unit}".strip()
        # Pattern: "550 bps"
        match = re.search(r'(\d+\.?\d*)\s*bps', rate_text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} bps"
        return ''

    def _detect_pik(self, rate_text: str, row_text: str) -> bool:
        """检测是否为PIK（实物支付利息）"""
        combined = (rate_text + ' ' + row_text).lower()
        return bool(re.search(r'\bpik\b|payment.in.kind|paid.in.kind', combined))

    def _extract_maturity(self, cell_texts: List[str]) -> str:
        """从单元格中提取到期日"""
        # 寻找日期格式
        date_patterns = [
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b',
            r'\b\d{1,2}/\d{4}\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        ]
        for cell in cell_texts:
            if not cell:
                continue
            for pattern in date_patterns:
                match = re.search(pattern, cell, re.IGNORECASE)
                if match:
                    return match.group(0)
        return ''

    def _extract_seniority(self, investment_type: str, row_text: str) -> str:
        """从投资类型和行文本中提取优先级"""
        combined = (investment_type + ' ' + row_text).lower()
        if 'first lien' in combined or 'senior secured' in combined or '1st lien' in combined:
            return 'First Lien'
        elif 'second lien' in combined or '2nd lien' in combined:
            return 'Second Lien'
        elif 'unitranche' in combined:
            return 'Unitranche'
        elif 'subordinated' in combined or 'mezzanine' in combined or 'mezz' in combined:
            return 'Subordinated'
        elif 'equity' in combined or 'stock' in combined or 'warrant' in combined:
            return 'Equity'
        elif 'unsecured' in combined:
            return 'Unsecured'
        elif 'senior' in combined:
            return 'Senior'
        return ''

    def _is_numeric(self, text: str) -> bool:
        """检查文本是否为数字"""
        if not text:
            return False
        # 移除常见的数字格式字符
        cleaned = text.replace(',', '').replace('$', '').replace('%', '').replace('(', '').replace(')', '').strip()
        try:
            float(cleaned)
            return True
        except:
            return False

    def _extract_quarter(self, period_of_report: str) -> str:
        """从period_of_report提取季度标签"""
        if not period_of_report:
            return ''

        # 期望格式: YYYY-MM-DD
        try:
            year = period_of_report[:4]
            month = period_of_report[5:7]

            # 根据月份确定季度
            month_int = int(month)
            if month_int in [1, 2, 3]:
                quarter = 'Q1'
            elif month_int in [4, 5, 6]:
                quarter = 'Q2'
            elif month_int in [7, 8, 9]:
                quarter = 'Q3'
            else:
                quarter = 'Q4'

            return f"{year}-{quarter}"
        except:
            return ''

    def _parse_fair_value(self, fair_value_raw: str) -> Optional[float]:
        """解析公允价值为浮点数（百万美元）"""
        if not fair_value_raw:
            return None

        try:
            # 处理负数括号表示法: (123) -> -123
            cleaned = fair_value_raw.replace('$', '').replace(',', '').strip()
            if cleaned.startswith('(') and cleaned.endswith(')'):
                cleaned = '-' + cleaned[1:-1]
            return float(cleaned)
        except:
            return None
