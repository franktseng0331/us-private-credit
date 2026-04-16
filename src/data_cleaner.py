"""
数据清洗主脚本 - 美国私募信贷 BDC 数据集

实现7个清洗步骤：
1. Investment Type 标准化
2. Industry 字段清洗 + GICS 宏观分类映射
3. 金额单位统一
4. 负值异常标记
5. 日期字段标准化
6. 利率字段补全（含 PIK 拆分）
7. 借款人名称标准化
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime
from typing import Dict, List, Tuple
import json


class BDCDataCleaner:
    """BDC 数据清洗器"""

    def __init__(self, input_csv: str):
        """初始化清洗器"""
        self.input_csv = input_csv
        self.df = None
        self.stats = {
            'step1_investment_type': {},
            'step2_industry': {},
            'step3_unit_conversion': {},
            'step4_negative_values': {},
            'step5_date_parsing': {},
            'step6_interest_rate': {},
            'step7_borrower_name': {}
        }

    def load_data(self):
        """加载原始数据"""
        print(f"加载数据: {self.input_csv}")
        self.df = pd.read_csv(self.input_csv, low_memory=False)
        print(f"总记录数: {len(self.df):,}")
        return self

    def step1_standardize_investment_type(self):
        """步骤1: Investment Type 标准化（优先级顺序匹配）"""
        print("\n步骤1: Investment Type 标准化...")

        def classify_investment_type(raw_type: str) -> str:
            """按优先级顺序分类投资类型"""
            if pd.isna(raw_type) or str(raw_type).strip() == '':
                return 'Unknown'

            raw_lower = str(raw_type).lower()

            # 优先级1-2: 复合条件（必须先匹配）
            if 'first lien' in raw_lower and 'delayed draw' in raw_lower:
                return 'First Lien Delayed Draw'
            if 'first lien' in raw_lower and 'revolver' in raw_lower:
                return 'First Lien Revolver'

            # 优先级3: Delayed Draw (单独)
            if 'delayed draw' in raw_lower:
                return 'First Lien Delayed Draw'

            # 优先级4-14: 单一条件
            if 'first lien' in raw_lower:
                return 'First Lien Term Loan'
            if 'second lien' in raw_lower:
                return 'Second Lien Term Loan'
            if 'unitranche' in raw_lower:
                return 'Unitranche Loan'
            if 'senior secured' in raw_lower or 'secured loan' in raw_lower:
                return 'Senior Secured Loan'
            if any(kw in raw_lower for kw in ['subordinated', 'mezzanine', 'mezz']):
                return 'Subordinated Debt'
            if any(kw in raw_lower for kw in ['clo', 'structured finance', 'structured note', 'structured product']):
                return 'Structured Finance / CLO'

            # Equity类型（扩展匹配）
            if any(kw in raw_lower for kw in ['common stock', 'common equity', 'common unit', 'class a unit', 'class a common']):
                return 'Common Equity'
            if 'preferred' in raw_lower:
                return 'Preferred Equity'
            if any(kw in raw_lower for kw in ['equity interest', 'equity', 'member unit', 'membership interest',
                                               'llc interest', 'llc unit', 'lp interest', "members' equity"]):
                return 'Common Equity'

            if 'warrant' in raw_lower:
                return 'Warrant'
            if any(kw in raw_lower for kw in ['unsecured note', 'senior note']):
                return 'Unsecured Note'

            # Revolver和Term Loan（通用）
            if 'revolving' in raw_lower or 'revolver' in raw_lower:
                return 'Revolver'
            if 'term loan' in raw_lower or 'term\n' in raw_lower:
                return 'Senior Secured Loan'

            # Growth Capital Loan
            if 'growth capital' in raw_lower:
                return 'Senior Secured Loan'

            # 优先级15: 无法匹配
            return 'Unknown'

        self.df['investment_type_std'] = self.df['investment_type'].apply(classify_investment_type)

        # 统计
        type_counts = self.df['investment_type_std'].value_counts()
        unknown_pct = (type_counts.get('Unknown', 0) / len(self.df)) * 100

        self.stats['step1_investment_type'] = {
            'total_records': len(self.df),
            'unknown_count': int(type_counts.get('Unknown', 0)),
            'unknown_percentage': round(unknown_pct, 2),
            'type_distribution': type_counts.to_dict()
        }

        print(f"  - Unknown 占比: {unknown_pct:.2f}% (目标 < 10%)")
        print(f"  - 标准类别数: {len(type_counts)}")

        return self

    def step2_clean_industry(self):
        """步骤2: Industry 字段清洗 + GICS 宏观分类"""
        print("\n步骤2: Industry 字段清洗 + GICS 映射...")

        # GICS 宏观分类映射（扩展关键词覆盖）
        gics_mapping = {
            'Software & Technology': [
                'software', 'application', 'technology', 'internet', 'saas', 'it services', 'data',
                'tech', 'cloud', 'semiconductor', 'electronic', 'cybersecurity', 'analytics',
                'information technology', 'digital', 'platform', 'systems', 'ai ', 'artificial intelligence',
                'telecom equipment', 'networking', 'hardware', 'it consulting', 'managed services',
                'infrastructure', 'devops', 'machine learning'
            ],
            'Healthcare': [
                'health care', 'healthcare', 'pharmaceutical', 'medical', 'biotech', 'life sciences',
                'hospital', 'health', 'clinical', 'dental', 'therapy', 'oncology', 'diagnostic',
                'drug', 'biopharma', 'physician', 'surgery', 'wellness', 'animal health',
                'home health', 'behavioral health', 'vision care', 'laboratory', 'care',
                'health & wellness', 'senior care', 'skilled nursing', 'rehabilitation',
                'specialty pharmacy', 'generic drug', 'contract research', 'cro '
            ],
            'Business Services': [
                'business services', 'staffing', 'consulting', 'professional services', 'human capital',
                'outsourc', 'administrative', 'facility', 'workforce', 'hr services', 'payroll',
                'security services', 'logistics', 'supply chain', 'commercial services',
                'diversified support services', 'support services', 'environmental services',
                'business process', 'document management', 'office services', 'office supplies',
                'research & consulting', 'fleet management', 'cleaning services',
                'transaction services', 'data processing', 'recruitment', 'testing & inspection',
                'research and consulting', 'human resources', 'commercial printing',
                'specialized consumer services', 'diversified commercial',
                'specialty distribution', 'security & alarm services', 'alarm services'
            ],
            'Financial Services': [
                'financial', 'insurance', 'banking', 'asset management', 'capital markets',
                'investment', 'brokerage', 'lending', 'credit', 'payment', 'fintech', 'mortgage',
                'specialized finance', 'diversified financial', 'multi-sector holdings', 'multi sector holdings',
                'thrift', 'consumer finance', 'exchange', 'wealth management', 'reinsurance',
                'private equity', 'venture capital', 'alternative investment',
                'diversified banks', 'banks', 'commercial banks'
            ],
            'Industrials': [
                'industrial', 'manufacturing', 'aerospace', 'defense', 'chemicals', 'machinery',
                'engineering', 'construction', 'building', 'material', 'packaging', 'printing',
                'mining', 'agriculture', 'aviation', 'waste management', 'environmental',
                'metal', 'glass', 'plastic', 'container', 'rubber', 'textile', 'fiber',
                'paper', 'lumber', 'forest', 'air freight', 'marine', 'railroad', 'trucking',
                'electrical equipment', 'auto component', 'auto part', 'vehicle', 'truck',
                'heavy equipment', 'pump', 'valve', 'tool', 'instrument', 'diversified industrial',
                'airport', 'ground transportation', 'courier', 'freight', 'cargo',
                'trading companies', 'distributors', 'distributor', 'trading company',
                'commercial vehicle', 'specialty chemical', 'diversified chemical',
                'industrial conglomerate', 'conglomerate'
            ],
            'Consumer': [
                'consumer', 'retail', 'food', 'beverage', 'restaurant', 'apparel',
                'household', 'personal care', 'pet', 'gaming', 'toy', 'e-commerce',
                'fashion', 'beauty', 'fitness', 'entertainment', 'hospitality', 'hotel', 'travel',
                'leisure', 'sport', 'home', 'footwear', 'shoe', 'clothing', 'housewares',
                'specialty retail', 'grocery', 'supermarket', 'drug store', 'pharmacy retail',
                'furniture', 'home furnishing', 'department store', 'discount store',
                'diversified consumer', 'tobacco', 'alcohol', 'spirits', 'wine', 'beer',
                'car rental', 'cruise', 'airline', 'recreation', 'amusement', 'casino', 'gambling',
                'personal product', 'cosmetic', 'jewelry', 'watch', 'luxury', 'gift', 'flower'
            ],
            'Energy': [
                'energy', 'oil', 'gas', 'power', 'utilities', 'renewable',
                'electric', 'solar', 'wind', 'pipeline', 'petroleum', 'fuel',
                'coal', 'nuclear', 'water utility', 'gas utility', 'electric utility',
                'exploration', 'production', 'refining', 'oilfield services'
            ],
            'Real Estate': [
                'real estate', 'reit', 'property', 'mortgage reit', 'equity reit',
                'commercial real estate', 'residential real estate', 'self-storage',
                'data center reit', 'industrial reit'
            ],
            'Media & Telecom': [
                'media', 'telecom', 'communication', 'broadcasting', 'cable',
                'publishing', 'advertising', 'marketing', 'digital media',
                'television', 'radio', 'content', 'streaming', 'wireless',
                'satellite', 'social media', 'online', 'news', 'film', 'music',
                'pr services', 'public relation', 'outdoor advertising',
                'alternative carrier', 'integrated telecom', 'wireless telecom',
                'telephone', 'cellular', 'broadband', 'fiber optic'
            ],
            'Education': [
                'education', 'training', 'learning', 'school', 'university', 'edtech',
                'childcare', 'child care', 'tutoring', 'test preparation', 'e-learning',
                'higher education', 'vocational', 'skills development'
            ],
            'Structured Finance': [
                'structured finance', 'clo', 'abs', 'securitization', 'structured product',
                'collateralized loan', 'collateralized debt', 'mbs', 'mortgage-backed',
                'asset-backed'
            ]
        }

        # 投资类型值（完全匹配，避免误清洗真实行业名）
        inv_type_values = {
            'senior secured', 'term loan', 'first lien term loan', 'second lien term loan',
            'delayed draw term loan', 'initial term loan', 'revolving loan', 'revolver',
            'first lien term loan a', 'first lien term loan b', 'term loan second lien',
            'initial term loan (second lien)', 'term loan (second lien)',
            'first out term loan', 'last out term loan', 'senior term loan a', 'senior term loan b',
            'super senior term loan b', 'first lein term loan', 'unsecured', 'convertible debt',
            'equity', 'class a membership units', 'class a units', 'class b preferred units',
            'lp units', 'llc interest', 'warrant', 'warrant class a', 'warrant class b',
            'warrant common stock', 'limited term royalty interest',
            'seventh amendment acquisition loan', 'senior notes', 'january 2027 notes', 'july 2029 notes',
            'promissory note', 'sub note', 'class a preferred units', 'eur term loan a', 'term loan (add on)'
        }

        def clean_industry_field(raw_industry: str) -> str:
            """清洗 industry 字段"""
            if pd.isna(raw_industry):
                return ''

            industry_str = str(raw_industry).strip()

            # 规则0: 空白字符（包括特殊空格）
            if industry_str == '' or industry_str == '​':
                return ''

            # 规则1: 脚注格式 (12) (13) 等
            if re.match(r'^\(\d+\)', industry_str) or re.match(r'^\(\d+\)\s*\(\d+\)', industry_str):
                return ''
            if re.match(r'^\(\d+\)$', industry_str):
                return ''

            industry_lower = industry_str.lower()

            # 规则2: 完全匹配投资类型值（不是部分匹配）
            if industry_lower in inv_type_values:
                return ''

            # 规则3: 公司名后缀（单独列值时）
            if industry_str in ['Inc.', 'LLC', 'Ltd.', 'Corp.', 'LP', 'Co.', 'PLC', 'N/A', 'NA']:
                return ''

            # 规则4: 单一特殊字符或纯符号
            if re.match(r'^[\$\*\-\—\–\.\#\&]+$', industry_str):
                return ''

            # 规则5: 纯数字或百分比（非行业名）
            if re.match(r'^[\d\.\%\,\s]+$', industry_str):
                return ''

            # 规则6: 极短值（1-2字符，非有效行业）
            if len(industry_str) <= 2:
                return ''

            # 规则7: 日期格式（M/D/YYYY 或 M/D/YY）
            if re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', industry_str):
                return ''

            # 规则8: 股权/权证类投资类型（误填到行业字段）
            equity_keywords = [
                'common stock', 'preferred stock', 'preferred equity', 'warrants', 'llc units', 'llc unit',
                'lp unit', 'lp units', 'class a units', 'class b units', 'class a membership units',
                'class b preferred units', 'membership units', 'membership interests', 'preferred units',
                'member units', 'junior equity', 'equity interests'
            ]
            if industry_lower in equity_keywords:
                return ''
            # 含数字的份额描述（如 "7,193,539.63 Preferred Units"）
            if re.match(r'^[\d,\.]+ ', industry_str):
                return ''
            # 含股份数量的描述（如 "927 shares of common stock"）
            if re.search(r'\bshares?\b', industry_lower):
                return ''

            # 规则9: 包含 "lien" 和 "loan" 的长描述（投资类型详细描述）
            if 'lien' in industry_lower and 'loan' in industry_lower:
                return ''
            if 'libor' in industry_lower or 'sofr' in industry_lower:
                return ''

            # 规则10: 列/表头标签（如 "Maturity / Expiration"）
            header_terms = ['maturity / expiration', 'maturity/expiration', 'gold', 'maturity']
            if industry_lower in header_terms:
                return ''

            # 规则11: 年份范围格式（如 "2025 Notes"）
            if re.match(r'^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\s+notes$', industry_lower):
                return ''

            # 规则12: Subordinated Securities 描述（投资类型）
            if 'subordinated securities' in industry_lower:
                return ''

            return industry_str

        def map_to_gics(industry_clean: str) -> str:
            """映射到 GICS 宏观大类"""
            if not industry_clean:
                return 'Other / Unknown'

            industry_lower = industry_clean.lower()

            for gics_category, keywords in gics_mapping.items():
                if any(kw in industry_lower for kw in keywords):
                    return gics_category

            return 'Other / Unknown'

        # 清洗 industry
        self.df['industry_clean'] = self.df['industry'].apply(clean_industry_field)

        # 映射到 GICS
        self.df['industry_gics'] = self.df['industry_clean'].apply(map_to_gics)

        # 跨季度回填（通过 borrower_name_clean，需先执行步骤7）
        # 这里先跳过，在步骤7后再回填

        # 统计
        valid_count = (self.df['industry_clean'] != '').sum()
        valid_pct = (valid_count / len(self.df)) * 100
        gics_counts = self.df['industry_gics'].value_counts()

        self.stats['step2_industry'] = {
            'total_records': len(self.df),
            'valid_count': int(valid_count),
            'valid_percentage': round(valid_pct, 2),
            'gics_distribution': gics_counts.to_dict()
        }

        print(f"  - 有效行业占比: {valid_pct:.2f}% (目标 > 60%)")
        print(f"  - GICS 大类数: {len(gics_counts)}")

        return self

    def step3_normalize_units(self):
        """步骤3: 金额单位统一（按 BDC + filing_id 分组）

        Bug fix (2026-04-16): 改进单位检测逻辑
        原因: 原阈值5000导致部分千美元/美元单位财报未转换，造成数据膨胀
        新逻辑:
        - max > 100000 → 美元单位（如TCPC的280M实际是280,464,610美元）
        - median > 100 → 千美元单位
        - median < 0.01 → 美元单位
        """
        print("\n步骤3: 金额单位统一...")

        conversion_log = []

        # 按 BDC + filing_id 分组
        for (cik, filing_id), group in self.df.groupby(['cik', 'filing_id']):
            # 计算该份财报的 fair_value 统计量
            fv_median = group['fair_value_usd_mn'].median()
            fv_max = group['fair_value_usd_mn'].max()
            fv_75th = group['fair_value_usd_mn'].quantile(0.75)

            if pd.isna(fv_median):
                continue

            # 判断单位（改进后的逻辑）
            # 规则1: max > 100000 → 美元
            # 极端大值说明单位是美元（如TCPC max=280,464,610美元=280M）
            if fv_max > 100000:
                factor = 1_000_000
                unit = 'dollars'
            # 规则2: 75th percentile > 1000 → 千美元
            # 大部分值都很大，说明单位是千美元
            elif fv_75th > 1000:
                factor = 1000
                unit = 'thousands'
            # 规则3: median > 100 → 千美元
            # 正常情况下单笔投资0.5M-100M，median > 100说明单位是千美元
            elif fv_median > 100:
                factor = 1000
                unit = 'thousands'
            # 规则4: median < 0.01 → 美元
            elif fv_median < 0.01:
                factor = 1_000_000
                unit = 'dollars'
            else:
                # 已经是百万美元
                continue

            # 修正该份财报的所有金额字段
            mask = (self.df['cik'] == cik) & (self.df['filing_id'] == filing_id)
            self.df.loc[mask, 'position_size_usd_mn'] /= factor
            self.df.loc[mask, 'cost_basis_usd_mn'] /= factor
            self.df.loc[mask, 'fair_value_usd_mn'] /= factor

            conversion_log.append({
                'cik': cik,
                'filing_id': filing_id,
                'original_unit': unit,
                'median_before': float(fv_median),
                'max_before': float(fv_max),
                'conversion_factor': factor,
                'records_affected': int(mask.sum())
            })

        self.stats['step3_unit_conversion'] = {
            'total_conversions': len(conversion_log),
            'conversion_log': conversion_log
        }

        print(f"  - 修正的财报数: {len(conversion_log)}")

        return self

    def step4_flag_negative_values(self):
        """步骤4: 负值异常标记（区分真实异常 vs 合理负值）"""
        print("\n步骤4: 负值异常标记...")

        # 初始化标记列
        self.df['is_anomaly'] = False
        self.df['is_unfunded_liability'] = False

        # 规则1: fair_value < 0 且为 Revolver/Delayed Draw → unfunded liability
        revolver_mask = (
            (self.df['fair_value_usd_mn'] < 0) &
            (self.df['investment_type_std'].str.contains('Revolver|Delayed Draw', case=False, na=False))
        )
        self.df.loc[revolver_mask, 'is_unfunded_liability'] = True

        # 规则2: fair_value < 0 且为普通 Term Loan → anomaly
        term_loan_mask = (
            (self.df['fair_value_usd_mn'] < 0) &
            (~self.df['investment_type_std'].str.contains('Revolver|Delayed Draw', case=False, na=False))
        )
        self.df.loc[term_loan_mask, 'is_anomaly'] = True

        # 规则3: cost_basis 或 position_size < 0 → anomaly
        cost_anomaly = self.df['cost_basis_usd_mn'] < 0
        position_anomaly = self.df['position_size_usd_mn'] < 0
        self.df.loc[cost_anomaly | position_anomaly, 'is_anomaly'] = True

        # 统计
        self.stats['step4_negative_values'] = {
            'unfunded_liability_count': int(revolver_mask.sum()),
            'anomaly_count': int(self.df['is_anomaly'].sum()),
            'negative_fair_value': int((self.df['fair_value_usd_mn'] < 0).sum()),
            'negative_cost_basis': int((self.df['cost_basis_usd_mn'] < 0).sum()),
            'negative_position_size': int((self.df['position_size_usd_mn'] < 0).sum())
        }

        print(f"  - Unfunded Liability: {revolver_mask.sum():,}")
        print(f"  - Anomaly: {self.df['is_anomaly'].sum():,}")

        return self

    def step5_standardize_dates(self):
        """步骤5: 日期字段标准化"""
        print("\n步骤5: 日期字段标准化...")

        def parse_maturity_date(raw_date: str, inv_type: str) -> str:
            """解析到期日"""
            if pd.isna(raw_date):
                return ''

            date_str = str(raw_date).strip()

            # 股权/权证类资产允许为空
            if inv_type in ['Common Equity', 'Preferred Equity', 'Warrant']:
                if date_str.lower() in ['n/a', 'perpetual', '']:
                    return ''

            # 格式1: Dec 2027
            match = re.match(r'([A-Za-z]{3})\s+(\d{4})', date_str)
            if match:
                month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
                month_str = match.group(1).lower()
                year = match.group(2)
                if month_str in month_map:
                    return f"{year}-{month_map[month_str]:02d}-01"

            # 格式2: 12/2027
            match = re.match(r'(\d{1,2})/(\d{4})', date_str)
            if match:
                month = int(match.group(1))
                year = match.group(2)
                return f"{year}-{month:02d}-01"

            # 格式3: 12/31/2027 或 12/31/27
            match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', date_str)
            if match:
                month = int(match.group(1))
                day = int(match.group(2))
                year = match.group(3)
                # 处理两位年份
                if len(year) == 2:
                    year_int = int(year)
                    year = f"20{year}" if year_int < 50 else f"19{year}"
                return f"{year}-{month:02d}-{day:02d}"

            # 格式4: 2027-12-31 (已标准化)
            if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                return date_str

            return ''

        self.df['maturity_date'] = self.df.apply(
            lambda row: parse_maturity_date(row['maturity_raw'], row['investment_type_std']),
            axis=1
        )

        # 统计（排除股权类资产）
        debt_mask = ~self.df['investment_type_std'].isin(['Common Equity', 'Preferred Equity', 'Warrant'])
        debt_records = self.df[debt_mask]
        parsed_count = (debt_records['maturity_date'] != '').sum()
        parse_rate = (parsed_count / len(debt_records)) * 100 if len(debt_records) > 0 else 0

        self.stats['step5_date_parsing'] = {
            'total_debt_records': int(len(debt_records)),
            'parsed_count': int(parsed_count),
            'parse_rate_percentage': round(parse_rate, 2)
        }

        print(f"  - 债务类资产解析成功率: {parse_rate:.2f}% (目标 > 80%)")

        return self

    def step6_extract_interest_rates(self):
        """步骤6: 利率字段补全（含 PIK 拆分）"""
        print("\n步骤6: 利率字段补全...")

        def extract_base_rate(rate_str: str) -> str:
            """提取基准利率"""
            if pd.isna(rate_str):
                return ''

            rate_lower = str(rate_str).lower()

            if 'sofr' in rate_lower or 's+' in rate_lower or 's +' in rate_lower:
                return 'SOFR'
            if 'libor' in rate_lower or 'l+' in rate_lower or 'l +' in rate_lower:
                return 'LIBOR'
            if 'prime' in rate_lower or 'p+' in rate_lower or 'p +' in rate_lower:
                return 'PRIME'
            if 'fixed' in rate_lower or re.match(r'^\d+\.?\d*%?$', rate_str.strip()):
                return 'Fixed'

            return ''

        def extract_spread_bps(rate_str: str) -> int:
            """提取总利差（基点）"""
            if pd.isna(rate_str):
                return 0

            rate_str = str(rate_str)

            # 匹配 +550 bps 或 +5.50%
            match = re.search(r'\+\s*(\d+\.?\d*)\s*(bps|%)', rate_str, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = match.group(2).lower()
                if unit == '%':
                    value *= 100  # 转换为基点
                return int(value)

            return 0

        def extract_pik_spread_bps(rate_str: str) -> int:
            """提取 PIK 利差（基点）"""
            if pd.isna(rate_str):
                return 0

            rate_str = str(rate_str)

            # 匹配 (1% PIK) 或 (100 bps PIK)
            match = re.search(r'\(?\s*(\d+\.?\d*)\s*(%|bps)?\s*PIK\s*\)?', rate_str, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = match.group(2)
                if unit and unit.lower() == '%':
                    value *= 100
                return int(value)

            return 0

        # 更新 base_rate
        self.df['base_rate'] = self.df['interest_rate_raw'].apply(extract_base_rate)

        # 新增 spread_bps
        self.df['spread_bps'] = self.df['interest_rate_raw'].apply(extract_spread_bps)

        # 新增 pik_spread_bps
        self.df['pik_spread_bps'] = self.df['interest_rate_raw'].apply(extract_pik_spread_bps)

        # 交叉验证 is_pik
        pik_mismatch = (self.df['pik_spread_bps'] > 0) & (self.df['is_pik'] == False)
        self.df.loc[pik_mismatch, 'is_pik'] = True

        # 统计
        base_rate_valid = (self.df['base_rate'] != '').sum()
        spread_valid = (self.df['spread_bps'] > 0).sum()
        pik_count = (self.df['pik_spread_bps'] > 0).sum()

        self.stats['step6_interest_rate'] = {
            'base_rate_valid_count': int(base_rate_valid),
            'spread_extracted_count': int(spread_valid),
            'pik_extracted_count': int(pik_count),
            'pik_is_pik_corrected': int(pik_mismatch.sum())
        }

        print(f"  - Base Rate 提取: {base_rate_valid:,}")
        print(f"  - Spread 提取: {spread_valid:,}")
        print(f"  - PIK 提取: {pik_count:,}")

        return self

    def step7_standardize_borrower_name(self):
        """步骤7: 借款人名称标准化"""
        print("\n步骤7: 借款人名称标准化...")

        def clean_borrower_name(raw_name: str) -> str:
            """标准化借款人名称"""
            if pd.isna(raw_name):
                return ''

            name = str(raw_name).strip()

            # 1. 转为全大写
            name = name.upper()

            # 2. 去除企业后缀
            suffixes = ['INC', 'LLC', 'LTD', 'CORP', 'LP', 'CO', 'HOLDINGS', 'GROUP', 'CORPORATION', 'LIMITED']
            for suffix in suffixes:
                # 匹配后缀（带或不带标点）
                name = re.sub(rf'\b{suffix}\.?\b', '', name, flags=re.IGNORECASE)

            # 3. 去除标点符号
            name = re.sub(r'[,.\-()\'\"&]', ' ', name)

            # 4. 去除多余空格
            name = ' '.join(name.split())

            return name.strip()

        self.df['borrower_name_clean'] = self.df['borrower_name'].apply(clean_borrower_name)

        # 统计
        unique_original = self.df['borrower_name'].nunique()
        unique_clean = self.df['borrower_name_clean'].nunique()
        reduction_pct = ((unique_original - unique_clean) / unique_original) * 100 if unique_original > 0 else 0

        self.stats['step7_borrower_name'] = {
            'unique_original': int(unique_original),
            'unique_clean': int(unique_clean),
            'reduction_percentage': round(reduction_pct, 2)
        }

        print(f"  - 原始唯一借款人: {unique_original:,}")
        print(f"  - 清洗后唯一借款人: {unique_clean:,}")
        print(f"  - 去重率: {reduction_pct:.2f}%")

        return self

    def step2_backfill_industry(self):
        """步骤2补充: 跨季度回填 industry（依赖步骤7）"""
        print("\n步骤2补充: 跨季度回填 industry...")

        # 构建借款人 → 有效行业的映射
        valid_industry = self.df[self.df['industry_clean'] != ''][['borrower_name_clean', 'industry_clean']]
        borrower_industry_map = valid_industry.groupby('borrower_name_clean')['industry_clean'].first().to_dict()

        # 回填空行业
        def backfill_industry(row):
            if row['industry_clean'] == '' and row['borrower_name_clean'] in borrower_industry_map:
                return borrower_industry_map[row['borrower_name_clean']]
            return row['industry_clean']

        before_backfill = (self.df['industry_clean'] != '').sum()
        self.df['industry_clean'] = self.df.apply(backfill_industry, axis=1)
        after_backfill = (self.df['industry_clean'] != '').sum()

        # 重新映射 GICS（使用与步骤2相同的完整映射字典）
        backfill_gics_mapping = {
            'Software & Technology': [
                'software', 'application', 'technology', 'internet', 'saas', 'it services', 'data',
                'tech', 'cloud', 'semiconductor', 'electronic', 'cybersecurity', 'analytics',
                'information technology', 'digital', 'platform', 'systems', 'ai ', 'artificial intelligence',
                'telecom equipment', 'networking', 'hardware', 'it consulting', 'managed services',
                'infrastructure', 'devops', 'machine learning'
            ],
            'Healthcare': [
                'health care', 'healthcare', 'pharmaceutical', 'medical', 'biotech', 'life sciences',
                'hospital', 'health', 'clinical', 'dental', 'therapy', 'oncology', 'diagnostic',
                'drug', 'biopharma', 'physician', 'surgery', 'wellness', 'animal health',
                'home health', 'behavioral health', 'vision care', 'laboratory', 'care',
                'health & wellness', 'senior care', 'skilled nursing', 'rehabilitation',
                'specialty pharmacy', 'generic drug', 'contract research', 'cro '
            ],
            'Business Services': [
                'business services', 'staffing', 'consulting', 'professional services', 'human capital',
                'outsourc', 'administrative', 'facility', 'workforce', 'hr services', 'payroll',
                'security services', 'logistics', 'supply chain', 'commercial services',
                'diversified support services', 'support services', 'environmental services',
                'business process', 'document management', 'office services', 'office supplies',
                'research & consulting', 'fleet management', 'cleaning services',
                'transaction services', 'data processing', 'recruitment', 'testing & inspection',
                'research and consulting', 'human resources', 'commercial printing',
                'specialized consumer services', 'diversified commercial',
                'specialty distribution', 'security & alarm services', 'alarm services'
            ],
            'Financial Services': [
                'financial', 'insurance', 'banking', 'asset management', 'capital markets',
                'investment', 'brokerage', 'lending', 'credit', 'payment', 'fintech', 'mortgage',
                'specialized finance', 'diversified financial', 'multi-sector holdings', 'multi sector holdings',
                'thrift', 'consumer finance', 'exchange', 'wealth management', 'reinsurance',
                'private equity', 'venture capital', 'alternative investment',
                'diversified banks', 'banks', 'commercial banks'
            ],
            'Industrials': [
                'industrial', 'manufacturing', 'aerospace', 'defense', 'chemicals', 'machinery',
                'engineering', 'construction', 'building', 'material', 'packaging', 'printing',
                'mining', 'agriculture', 'aviation', 'waste management', 'environmental',
                'metal', 'glass', 'plastic', 'container', 'rubber', 'textile', 'fiber',
                'paper', 'lumber', 'forest', 'air freight', 'marine', 'railroad', 'trucking',
                'electrical equipment', 'auto component', 'auto part', 'vehicle', 'truck',
                'heavy equipment', 'pump', 'valve', 'tool', 'instrument', 'diversified industrial',
                'airport', 'ground transportation', 'courier', 'freight', 'cargo',
                'trading companies', 'distributors', 'distributor', 'trading company',
                'commercial vehicle', 'specialty chemical', 'diversified chemical',
                'industrial conglomerate', 'conglomerate', 'automobile'
            ],
            'Consumer': [
                'consumer', 'retail', 'food', 'beverage', 'restaurant', 'apparel',
                'household', 'personal care', 'pet', 'gaming', 'toy', 'e-commerce',
                'fashion', 'beauty', 'fitness', 'entertainment', 'hospitality', 'hotel', 'travel',
                'leisure', 'sport', 'home', 'footwear', 'shoe', 'clothing', 'housewares',
                'specialty retail', 'grocery', 'supermarket', 'drug store', 'pharmacy retail',
                'furniture', 'home furnishing', 'department store', 'discount store',
                'diversified consumer', 'tobacco', 'alcohol', 'spirits', 'wine', 'beer',
                'car rental', 'cruise', 'airline', 'recreation', 'amusement', 'casino', 'gambling',
                'personal product', 'cosmetic', 'jewelry', 'watch', 'luxury', 'gift', 'flower'
            ],
            'Energy': [
                'energy', 'oil', 'gas', 'power', 'utilities', 'renewable',
                'electric', 'solar', 'wind', 'pipeline', 'petroleum', 'fuel',
                'coal', 'nuclear', 'water utility', 'gas utility', 'electric utility',
                'exploration', 'production', 'refining', 'oilfield services'
            ],
            'Real Estate': [
                'real estate', 'reit', 'property', 'mortgage reit', 'equity reit',
                'commercial real estate', 'residential real estate', 'self-storage',
                'data center reit', 'industrial reit'
            ],
            'Media & Telecom': [
                'media', 'telecom', 'communication', 'broadcasting', 'cable',
                'publishing', 'advertising', 'marketing', 'digital media',
                'television', 'radio', 'content', 'streaming', 'wireless',
                'satellite', 'social media', 'online', 'news', 'film', 'music',
                'pr services', 'public relation', 'outdoor advertising',
                'alternative carrier', 'integrated telecom', 'wireless telecom',
                'telephone', 'cellular', 'broadband', 'fiber optic'
            ],
            'Education': [
                'education', 'training', 'learning', 'school', 'university', 'edtech',
                'childcare', 'child care', 'tutoring', 'test preparation', 'e-learning',
                'higher education', 'vocational', 'skills development'
            ],
            'Structured Finance': [
                'structured finance', 'clo', 'abs', 'securitization', 'structured product',
                'collateralized loan', 'collateralized debt', 'mbs', 'mortgage-backed',
                'asset-backed'
            ]
        }

        def map_to_gics_backfill(industry_clean: str) -> str:
            if not industry_clean:
                return 'Other / Unknown'
            industry_lower = industry_clean.lower()
            for gics_category, keywords in backfill_gics_mapping.items():
                if any(kw in industry_lower for kw in keywords):
                    return gics_category
            return 'Other / Unknown'

        self.df['industry_gics'] = self.df['industry_clean'].apply(map_to_gics_backfill)

        backfilled_count = after_backfill - before_backfill
        self.stats['step2_industry']['backfilled_count'] = int(backfilled_count)
        self.stats['step2_industry']['valid_count_after_backfill'] = int(after_backfill)
        self.stats['step2_industry']['valid_percentage_after_backfill'] = round((after_backfill / len(self.df)) * 100, 2)

        print(f"  - 回填记录数: {backfilled_count:,}")
        print(f"  - 回填后有效率: {self.stats['step2_industry']['valid_percentage_after_backfill']:.2f}%")

        return self

    def save_results(self, output_csv: str, report_json: str):
        """保存清洗结果"""
        print(f"\n保存清洗结果...")

        # 保存 CSV
        self.df.to_csv(output_csv, index=False)
        print(f"  - 清洗数据: {output_csv}")
        print(f"  - 总记录数: {len(self.df):,}")
        print(f"  - 总字段数: {len(self.df.columns)}")

        # 保存报告
        report = {
            'cleaning_date': datetime.now().isoformat(),
            'input_file': self.input_csv,
            'output_file': output_csv,
            'total_records': len(self.df),
            'total_columns': len(self.df.columns),
            'new_columns': [
                'investment_type_std', 'industry_clean', 'industry_gics',
                'borrower_name_clean', 'maturity_date', 'spread_bps',
                'pik_spread_bps', 'is_anomaly', 'is_unfunded_liability'
            ],
            'statistics': self.stats
        }

        with open(report_json, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"  - 清洗报告: {report_json}")

        return self


def main():
    """主函数"""
    import os

    # 路径配置
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_csv = os.path.join(base_dir, 'data/parsed/deal_positions.csv')
    output_dir = os.path.join(base_dir, 'data/cleaned')
    os.makedirs(output_dir, exist_ok=True)

    output_csv = os.path.join(output_dir, 'deal_positions_clean.csv')
    report_json = os.path.join(output_dir, 'cleaning_report.json')

    # 执行清洗
    cleaner = BDCDataCleaner(input_csv)

    cleaner.load_data() \
           .step1_standardize_investment_type() \
           .step2_clean_industry() \
           .step3_normalize_units() \
           .step4_flag_negative_values() \
           .step5_standardize_dates() \
           .step6_extract_interest_rates() \
           .step7_standardize_borrower_name() \
           .step2_backfill_industry() \
           .save_results(output_csv, report_json)

    print("\n✓ 数据清洗完成")


if __name__ == '__main__':
    main()
