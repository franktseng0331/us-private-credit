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
        seen_table_ids = set()
        for i, table in enumerate(tables):
            # Normalize: replace non-breaking spaces (\xa0) and collapse whitespace variants
            raw_text = table.get_text().replace('\xa0', ' ')
            table_text = raw_text.lower()

            # Some BDCs write "FairValue" without space — use regex for robustness
            has_fair_value = bool(re.search(r'fair\s*value', table_text))

            # 识别投资表格的特征（多模式匹配，覆盖 ARCC/MAIN/NMFC/BXSL/GBDC/CGBD/SLRC 等格式）
            matched = False
            if ('portfolio company' in table_text and has_fair_value):
                matched = True
            elif (('borrower' in table_text or 'company' in table_text) and
                (has_fair_value or 'principal' in table_text) and
                ('coupon' in table_text or 'interest rate' in table_text or 'spread' in table_text)):
                matched = True
            # BXSL/GBDC/CGBD/SLRC: "investments" header + rate/spread + maturity
            elif (('investments' in table_text or 'description' in table_text) and
                  ('spread' in table_text or 'interest rate' in table_text or 'reference rate' in table_text) and
                  ('maturity' in table_text or 'principal' in table_text or 'par' in table_text) and
                  has_fair_value):
                matched = True

            if matched:
                # Deduplicate: use first 300 chars of normalized text as key
                tbl_key = table_text[:300]
                if tbl_key not in seen_table_ids:
                    seen_table_ids.add(tbl_key)
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

        # Detect table layout by examining first few rows with content
        layout = self._detect_table_layout(rows)

        # 要排除的非投资行关键词
        exclude_keywords = [
            'total', 'subtotal', 'interest receivable', 'fee payable',
            'payable', 'receivable', 'total investments', 'total portfolio',
            'percentage', 'as of', 'unaudited', 'see notes',
            'fair value at', 'additions', 'reductions', 'unrealized',
            'fair value, beginning', 'fair value, end',
        ]

        # Section-header keywords: rows that are category labels, not actual positions
        section_keywords = [
            'first lien', 'second lien', 'third lien', 'subordinated',
            'mezzanine', 'equity investments', 'debt investments',
            'non-controlled', 'controlled', 'affiliated', 'unaffiliated',
            'unfunded', 'senior secured loans', 'equipment financing',
        ]

        # 解析数据行
        current_company = None
        current_industry = None
        current_section_type = None  # investment type inferred from section label (BXSL/SLRC)
        header_row_idx = layout.get('header_row_idx', 0)

        filing_id = metadata.get('accession_number', '')
        is_amended = bool(filing_id and ('/A' in filing_id or filing_id.endswith('-A')))
        quarter = self._extract_quarter(metadata.get('period_of_report', ''))

        for row in rows[header_row_idx + 1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                # Single-cell colspan row — may be section/type header (BXSL 2025+ style)
                single_text = cells[0].get_text().strip().replace('\xa0', ' ') if cells else ''
                if single_text and not self._is_numeric(single_text) and len(single_text) > 2:
                    fc_lower = single_text.lower()
                    inv_type_kw = [
                        'first lien', 'second lien', 'third lien', 'equity', 'subordinated',
                        'mezzanine', 'debt', 'unitranche', 'one stop', 'senior secured',
                        'unfunded', 'non-controlled', 'controlled', 'affiliated',
                    ]
                    if any(kw in fc_lower for kw in inv_type_kw):
                        current_section_type = single_text
                    else:
                        current_industry = single_text
                continue

            cell_texts = [cell.get_text().strip().replace('\xa0', ' ') for cell in cells]
            non_empty = [t for t in cell_texts if t]

            # Skip truly empty rows
            if not non_empty:
                continue

            row_text_lower = ' '.join(cell_texts).lower()

            # Skip aggregate/summary rows
            if any(keyword in row_text_lower for keyword in exclude_keywords):
                continue

            # Count non-empty cells to detect section-header rows (≤2 non-empty, no numerics)
            non_empty_count = sum(1 for t in cell_texts if t)
            is_solo_text_row = (
                non_empty_count <= 2 and
                not any(self._is_numeric(t) for t in cell_texts) and
                not re.search(r'(SOFR|LIBOR|Prime|L\s*\+|S\s*\+|\+\s*\d)', row_text_lower, re.IGNORECASE)
            )

            # First col is non-numeric text that looks like a company/description
            first_col = cell_texts[0] if cell_texts else None
            col0_is_name = (
                first_col and
                not self._is_numeric(first_col) and
                len(first_col) > 3 and
                not any(kw in first_col.lower() for kw in ['total', 'subtotal', 'sum', 'aggregate'])
            )

            if layout['style'] == 'compact':
                # Standard layout: company name at col 0, investment type at col 1 or 2
                if col0_is_name:
                    if is_solo_text_row or any(kw in first_col.lower() for kw in section_keywords):
                        if any(kw in first_col.lower() for kw in section_keywords):
                            current_industry = first_col
                        else:
                            current_company = first_col
                            if len(cell_texts) > 1 and cell_texts[1] and not self._is_numeric(cell_texts[1]):
                                candidate = cell_texts[1]
                                if not any(kw in candidate.lower() for kw in section_keywords):
                                    current_industry = candidate
                    else:
                        current_company = first_col
                        if len(cell_texts) > 1 and cell_texts[1] and not self._is_numeric(cell_texts[1]):
                            candidate = cell_texts[1]
                            if not any(kw in candidate.lower() for kw in section_keywords):
                                current_industry = candidate

                investment_type = self._find_investment_type(cell_texts, max_col=8)

            elif layout['style'] == 'sparse':
                # BXSL/GBDC/CGBD/SLRC: wide tables with many sparse columns.
                # Company name is usually at col 0, but GBDC puts it at col 1 (col 0 empty).
                # Detect effective first column (first non-empty col in row).
                effective_col = None
                effective_text = None
                for ci, ct in enumerate(cell_texts[:5]):
                    if ct:
                        effective_col = ci
                        effective_text = ct
                        break

                eff_is_name = (
                    effective_text and
                    not self._is_numeric(effective_text) and
                    len(effective_text) > 3 and
                    not any(kw in effective_text.lower() for kw in ['total', 'subtotal', 'sum', 'aggregate'])
                )

                if is_solo_text_row and eff_is_name:
                    fc_lower = effective_text.lower()
                    inv_type_keywords = [
                        'first lien', 'second lien', 'third lien', 'senior secured', 'senior loan',
                        'subordinated', 'mezzanine', 'equity investment', 'debt investment',
                        'one stop', 'unitranche', 'equipment financing', 'unfunded',
                        'non-controlled', 'controlled', 'affiliated',
                    ]
                    is_inv_type_header = any(kw in fc_lower for kw in inv_type_keywords)
                    is_inv_type_header = is_inv_type_header or bool(re.search(r'[—–]\s*\d+\.?\d*%', effective_text))

                    if is_inv_type_header:
                        current_section_type = effective_text
                        current_industry = None
                    else:
                        current_industry = effective_text
                    continue

                if eff_is_name and not is_solo_text_row:
                    # Data row: company at effective_col
                    raw_company = effective_text
                    # BXSL embeds type in name: "ABC Corp - Common Stock (4)" → split on " - "
                    company_name, embedded_type = self._split_company_type(raw_company)
                    current_company = company_name

                    # Industry: look for non-numeric, non-rate text in cols after effective_col
                    for ci in range(effective_col + 1, min(len(cell_texts), effective_col + 10)):
                        candidate = cell_texts[ci]
                        if (candidate and not self._is_numeric(candidate) and
                                len(candidate) > 3 and
                                not re.match(r'^\(?[\d\(\)\s]+\)?$', candidate) and
                                not re.search(r'(SOFR|LIBOR|L\s*\+|S\s*\+|\+|\d+\.?\d*\s*%)', candidate, re.IGNORECASE)):
                            current_industry = candidate
                            break

                    # Investment type: embedded in name first, then search cells, then section context
                    investment_type = embedded_type
                    if not investment_type:
                        investment_type = self._find_investment_type(cell_texts, max_col=len(cell_texts))
                    if not investment_type and current_section_type:
                        investment_type = self._infer_type_from_section(current_section_type)
                    if not investment_type:
                        investment_type = self._infer_type_from_section(current_industry or '')
                else:
                    continue

            else:
                # Multi-row (NMFC/BXSL wide tables): company name row has no investment type
                # in same row; investment type appears in subsequent data rows.
                # BXSL wide tables embed type in name: "ABC Corp - Common Stock (4)"
                if col0_is_name and is_solo_text_row:
                    fc_lower = first_col.lower()
                    if any(kw in fc_lower for kw in section_keywords):
                        current_section_type = first_col
                    else:
                        # May be "Company - Type" embedded — split it
                        split_name, split_type = self._split_company_type(first_col)
                        current_company = split_name
                        if split_type:
                            current_section_type = split_type
                        current_industry = None
                    continue
                elif col0_is_name and not is_solo_text_row:
                    split_name, split_type = self._split_company_type(first_col)
                    current_company = split_name
                    if len(cell_texts) > 1 and cell_texts[1] and not self._is_numeric(cell_texts[1]):
                        current_industry = cell_texts[1]
                else:
                    split_type = None

                # Search cells starting at col 1 to avoid matching keywords in company name
                investment_type = split_type if split_type else self._find_investment_type(cell_texts[1:], max_col=len(cell_texts))
                if not investment_type and current_section_type:
                    investment_type = self._infer_type_from_section(current_section_type)

            # Must have investment type to create a record
            if not investment_type:
                continue

            # --- Extract rate fields ---
            interest_rate_raw = self._find_interest_rate(cell_texts)
            base_rate = self._extract_base_rate(interest_rate_raw) if interest_rate_raw else ''
            spread_raw = self._extract_spread(interest_rate_raw) if interest_rate_raw else ''
            is_pik = self._detect_pik(interest_rate_raw or '', row_text_lower)

            # --- Extract maturity ---
            maturity_raw = self._extract_maturity(cell_texts)

            # --- Extract seniority ---
            seniority = self._extract_seniority(investment_type, row_text_lower)

            # --- Extract numeric financial data ---
            numeric_values = []
            for cell in cell_texts:
                if cell and self._is_numeric(cell):
                    try:
                        val = float(cell.replace(',', '').replace('(', '-').replace(')', ''))
                        numeric_values.append((cell, val))
                    except:
                        pass

            # Fair value: last non-negative numeric in trailing cells
            fair_value = None
            for cell in reversed(cell_texts[-15:]):
                if cell and self._is_numeric(cell):
                    try:
                        val = float(cell.replace(',', '').replace('(', '-').replace(')', ''))
                        if val >= 0:
                            fair_value = cell
                            break
                    except:
                        pass

            position_size_raw = None
            cost_basis_raw = None
            if len(numeric_values) >= 3:
                position_size_raw = numeric_values[-3][0]
                cost_basis_raw = numeric_values[-2][0]
            elif len(numeric_values) >= 2:
                cost_basis_raw = numeric_values[-2][0]

            if current_company and investment_type and (fair_value is not None or position_size_raw):
                fv_parsed = self._parse_fair_value(fair_value) if fair_value is not None else 0.0

                record = {
                    'cik': metadata['cik'],
                    'bdc_name': metadata.get('ticker', ''),
                    'ticker': metadata.get('ticker', ''),
                    'filing_type': metadata.get('filing_type', '10-Q'),
                    'filing_date': metadata['filing_date'],
                    'period_of_report': metadata.get('period_of_report', ''),
                    'quarter': quarter,
                    'borrower_name': current_company,
                    'industry': current_industry or '',
                    'investment_type': investment_type,
                    'seniority': seniority,
                    'is_pik': is_pik,
                    'interest_rate_raw': interest_rate_raw or '',
                    'base_rate': base_rate or '',
                    'spread_raw': spread_raw or '',
                    'maturity_raw': maturity_raw or '',
                    'position_size_usd_mn': self._parse_fair_value(position_size_raw),
                    'cost_basis_usd_mn': self._parse_fair_value(cost_basis_raw),
                    'fair_value_raw': fair_value or '0',
                    'fair_value_usd_mn': fv_parsed,
                    'data_source': 'HTML',
                    'filing_id': filing_id,
                    'is_amended': is_amended,
                    'raw_row': ' | '.join(cell_texts[:10])
                }
                records.append(record)

        return records

    def _detect_table_layout(self, rows) -> dict:
        """
        Determine the table layout style by examining the first content rows.

        Returns dict with 'style' ('compact', 'sparse', 'multirow') and 'header_row_idx'.

        - compact: standard layout, company + investment type on same row, dense columns
        - sparse: company + industry on same row, financial data spread across many sparse cols (GBDC/BXSL/CGBD/SLRC)
        - multirow: company name on its own row, investment rows follow (NMFC)
        """
        header_row_idx = 0
        max_cols = 0
        first_data_rows = []

        for i, row in enumerate(rows[:8]):
            cells = row.find_all(['td', 'th'])
            cell_texts = [c.get_text(strip=True) for c in cells]
            non_empty = [t for t in cell_texts if t]
            if not non_empty:
                continue

            row_text = ' '.join(cell_texts).lower()
            # Look for header row
            if any(kw in row_text for kw in ['investment type', 'portfolio company', 'description',
                                               'investments', 'reference rate', 'spread above']):
                header_row_idx = i

            max_cols = max(max_cols, len(cells))
            first_data_rows.append((i, cell_texts))

        # Determine style
        if max_cols > 12:
            # Very wide tables → sparse layout (GBDC uses 30+ cols)
            # Check if company-name rows have only 1 non-empty cell AT COL 0 → multirow
            # (GBDC has solo-text rows at col 1, not col 0 — those are section headers in sparse)
            solo_name_rows_at_col0 = 0
            data_rows_checked = 0
            section_kw = [
                # Industry/sector keywords
                'software', 'healthcare', 'health care', 'services', 'technology',
                'media', 'telecom', 'energy', 'industrial', 'financial', 'consumer',
                'materials', 'real estate', 'utilities', 'retail', 'education',
                'transportation', 'infrastructure', 'aerospace', 'defense',
                'food', 'beverage', 'insurance', 'banking', 'diversified',
                # Investment-type header keywords (BXSL 2025+ uses colspan rows for these)
                'first lien', 'second lien', 'third lien', 'senior secured',
                'subordinated', 'mezzanine', 'unitranche', 'one stop',
                'equity investment', 'debt investment', 'non-controlled', 'controlled',
            ]
            for _, ct in first_data_rows[header_row_idx:header_row_idx + 8]:
                non_empty_positions = [(idx, t) for idx, t in enumerate(ct) if t]
                if (len(non_empty_positions) == 1 and
                        non_empty_positions[0][0] == 0 and
                        not self._is_numeric(non_empty_positions[0][1]) and
                        len(non_empty_positions[0][1]) > 3):
                    cell_lower = non_empty_positions[0][1].lower()
                    # Skip industry/type header rows — they should not trigger multirow
                    if not any(kw in cell_lower for kw in section_kw):
                        solo_name_rows_at_col0 += 1
                data_rows_checked += 1

            if solo_name_rows_at_col0 >= 1 and data_rows_checked > 0:
                style = 'multirow'
            else:
                style = 'sparse'
        else:
            style = 'compact'

        return {'style': style, 'header_row_idx': header_row_idx}

    def _find_investment_type(self, cell_texts: list, max_col: int = 8) -> str:
        """Search cell_texts up to max_col for investment type keywords."""
        type_keywords = [
            'first lien', 'second lien', 'third lien', 'senior secured',
            'loan', 'equity', 'stock', 'units', 'warrant', 'note',
            'one stop', 'senior loan', 'revolver', 'term loan', 'delayed draw',
            'subordinated', 'mezzanine', 'bond', 'preferred',
        ]
        for cell in cell_texts[:max_col]:
            if not cell:
                continue
            cl = cell.lower()
            if any(kw in cl for kw in type_keywords):
                return cell
        return None

    def _split_company_type(self, company_str: str):
        """Split 'ABC Corp - Common Stock (4)' → ('ABC Corp', 'Common Stock').
        Returns (company_name, investment_type_or_None)."""
        if ' - ' not in company_str:
            return company_str, None
        type_keywords = [
            'loan', 'equity', 'stock', 'units', 'warrant', 'note',
            'revolver', 'term loan', 'delayed draw', 'subordinated',
            'mezzanine', 'bond', 'preferred', 'lien', 'interest',
        ]
        parts = company_str.split(' - ')
        # Check if the last part looks like an investment type
        suffix = parts[-1].strip()
        # Strip all trailing footnote markers like "(4)(5)(7)"
        suffix_clean = re.sub(r'(\s*\(\d+\))+\s*$', '', suffix).strip()
        if any(kw in suffix_clean.lower() for kw in type_keywords):
            company = ' - '.join(parts[:-1]).strip()
            return company, suffix_clean
        return company_str, None

    def _infer_type_from_section(self, section_text: str) -> str:
        """Map section label → standardised investment type string."""
        if not section_text:
            return ''
        s = section_text.lower()
        if 'first lien' in s or '1st lien' in s:
            return 'First Lien Term Loan'
        if 'second lien' in s or '2nd lien' in s:
            return 'Second Lien Term Loan'
        if 'third lien' in s or '3rd lien' in s:
            return 'Third Lien Term Loan'
        if 'unitranche' in s or 'one stop' in s:
            return 'Unitranche Term Loan'
        if 'senior secured' in s:
            return 'Senior Secured Term Loan'
        if 'senior loan' in s:
            return 'Senior Secured Term Loan'
        if 'subordinated' in s or 'mezzanine' in s or 'mezz' in s:
            return 'Subordinated Note'
        if 'equity' in s:
            return 'Equity'
        if 'warrant' in s:
            return 'Warrant'
        if 'preferred' in s:
            return 'Preferred Stock'
        if 'equipment' in s:
            return 'Equipment Financing'
        if 'debt' in s:
            return 'Term Loan'
        return ''

    def _find_interest_rate(self, cell_texts: list) -> str:
        """Find the interest rate / spread cell in a row."""
        # Prefer SOFR/LIBOR+spread format
        for cell in cell_texts:
            if cell and re.search(r'(SOFR|LIBOR|Prime|L\s*\+|S\s*\+)', cell, re.IGNORECASE):
                return cell
        # Then % cells
        for cell in cell_texts:
            if cell and '%' in cell:
                cleaned = cell.replace('%', '').replace('+', '').strip()
                if self._is_numeric(cleaned):
                    return cell
        # Then bps/spread patterns
        for cell in cell_texts:
            if cell and re.search(r'\d+\.?\d*\s*(bps|basis|\+)', cell, re.IGNORECASE):
                return cell
        return None

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
        # Reject footnote markers like (2)(6)(11) — multiple parenthesized integers
        if re.match(r'^(\(\d+\))+$', text.strip()):
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
