"""
数据验证器
检查数据质量、覆盖率和完整性
"""
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataValidator:
    """数据质量验证器"""

    def __init__(self, data_path: str = "data/parsed/deal_positions.csv",
                 config_path: str = "config/bdc_ciks.json"):
        """
        初始化验证器

        Args:
            data_path: 数据文件路径
            config_path: BDC配置文件路径
        """
        self.data_path = Path(data_path)
        self.config_path = Path(config_path)

        # 必填字段
        self.required_fields = [
            'cik', 'bdc_name', 'ticker', 'filing_date',
            'borrower_name', 'fair_value_usd_mn'
        ]

        # 预期季度数（2021-Q1到2025-Q4）
        self.expected_quarters = self._generate_quarters(2021, 2025)

    def _generate_quarters(self, start_year: int, end_year: int) -> List[str]:
        """生成预期的季度列表"""
        quarters = []
        for year in range(start_year, end_year + 1):
            for q in range(1, 5):
                quarters.append(f"{year}-Q{q}")
        return quarters

    def validate_data(self) -> Dict:
        """
        执行完整的数据验证

        Returns:
            验证报告字典
        """
        logger.info("开始数据验证...")

        if not self.data_path.exists():
            logger.error(f"数据文件不存在: {self.data_path}")
            return {"error": "数据文件不存在"}

        # 读取数据
        df = pd.read_csv(self.data_path)
        logger.info(f"读取了 {len(df)} 条记录")

        # 执行各项检查
        report = {
            "total_records": len(df),
            "validation_time": pd.Timestamp.now().isoformat(),
            "completeness": self._check_completeness(df),
            "coverage": self._check_coverage(df),
            "data_quality": self._check_data_quality(df),
            "anomalies": self._check_anomalies(df)
        }

        # 保存报告
        self._save_report(report, "data/parsed/quality_report.json")

        # 生成覆盖率报告
        coverage_report = self._generate_coverage_report(df)
        self._save_report(coverage_report, "data/parsed/coverage_report.json")

        logger.info("验证完成！")
        return report

    def _check_completeness(self, df: pd.DataFrame) -> Dict:
        """检查字段完整性"""
        completeness = {}

        for field in self.required_fields:
            if field in df.columns:
                missing_count = df[field].isna().sum()
                missing_rate = missing_count / len(df) * 100
                completeness[field] = {
                    "missing_count": int(missing_count),
                    "missing_rate": round(missing_rate, 2),
                    "status": "PASS" if missing_rate < 5 else "FAIL"
                }
            else:
                completeness[field] = {
                    "missing_count": len(df),
                    "missing_rate": 100.0,
                    "status": "FAIL"
                }

        return completeness

    def _check_coverage(self, df: pd.DataFrame) -> Dict:
        """检查季度覆盖率"""
        coverage = {}

        if 'ticker' not in df.columns or 'quarter' not in df.columns:
            return {"error": "缺少ticker或quarter字段"}

        # 按BDC统计覆盖的季度
        for ticker in df['ticker'].unique():
            bdc_data = df[df['ticker'] == ticker]
            covered_quarters = bdc_data['quarter'].unique().tolist()

            coverage[ticker] = {
                "expected_quarters": len(self.expected_quarters),
                "actual_quarters": len(covered_quarters),
                "coverage_rate": round(len(covered_quarters) / len(self.expected_quarters) * 100, 2),
                "missing_quarters": [q for q in self.expected_quarters if q not in covered_quarters]
            }

        return coverage

    def _check_data_quality(self, df: pd.DataFrame) -> Dict:
        """检查数据质量"""
        quality = {}

        # 检查数值字段
        numeric_fields = ['fair_value_usd_mn', 'cost_basis_usd_mn', 'position_size_usd_mn']

        for field in numeric_fields:
            if field in df.columns:
                valid_data = df[field].dropna()
                if len(valid_data) > 0:
                    quality[field] = {
                        "min": float(valid_data.min()),
                        "max": float(valid_data.max()),
                        "mean": float(valid_data.mean()),
                        "median": float(valid_data.median()),
                        "negative_count": int((valid_data < 0).sum())
                    }

        # 检查借款人名称去重效果
        if 'borrower_name' in df.columns:
            unique_borrowers = df['borrower_name'].nunique()
            total_records = len(df)
            quality['borrower_deduplication'] = {
                "unique_borrowers": unique_borrowers,
                "total_records": total_records,
                "duplication_rate": round((1 - unique_borrowers / total_records) * 100, 2)
            }

        return quality

    def _check_anomalies(self, df: pd.DataFrame) -> Dict:
        """检查异常值"""
        anomalies = {}

        # 检查负数fair_value
        if 'fair_value_usd_mn' in df.columns:
            negative_fv = df[df['fair_value_usd_mn'] < 0]
            anomalies['negative_fair_value'] = {
                "count": len(negative_fv),
                "examples": negative_fv[['ticker', 'borrower_name', 'fair_value_usd_mn']].head(5).to_dict('records')
            }

        # 检查fair_value与cost_basis差异过大的情况
        if 'fair_value_usd_mn' in df.columns and 'cost_basis_usd_mn' in df.columns:
            df_valid = df.dropna(subset=['fair_value_usd_mn', 'cost_basis_usd_mn'])
            df_valid['fv_cost_ratio'] = df_valid['fair_value_usd_mn'] / df_valid['cost_basis_usd_mn']

            # 标记偏离超过50%的记录
            large_deviation = df_valid[(df_valid['fv_cost_ratio'] < 0.5) | (df_valid['fv_cost_ratio'] > 1.5)]
            anomalies['large_fv_cost_deviation'] = {
                "count": len(large_deviation),
                "examples": large_deviation[['ticker', 'borrower_name', 'fair_value_usd_mn', 'cost_basis_usd_mn']].head(5).to_dict('records')
            }

        # 检查缺失利率的记录
        if 'interest_rate_raw' in df.columns:
            missing_rate = df[df['interest_rate_raw'].isna()]
            anomalies['missing_interest_rate'] = {
                "count": len(missing_rate),
                "rate": round(len(missing_rate) / len(df) * 100, 2)
            }

        return anomalies

    def _generate_coverage_report(self, df: pd.DataFrame) -> Dict:
        """生成详细的覆盖率报告"""
        coverage_report = {}

        if 'ticker' not in df.columns or 'quarter' not in df.columns:
            return {"error": "缺少ticker或quarter字段"}

        # 加载BDC配置
        with open(self.config_path, 'r') as f:
            bdc_config = json.load(f)

        for ticker, info in bdc_config.items():
            bdc_data = df[df['ticker'] == ticker]
            covered_quarters = sorted(bdc_data['quarter'].unique().tolist())

            coverage_report[ticker] = {
                "cik": info['cik'],
                "name": info['name'],
                "expected_quarters": len(self.expected_quarters),
                "actual_quarters": len(covered_quarters),
                "coverage_rate": round(len(covered_quarters) / len(self.expected_quarters) * 100, 2),
                "covered_quarters": covered_quarters,
                "missing_quarters": [q for q in self.expected_quarters if q not in covered_quarters],
                "total_records": len(bdc_data)
            }

        return coverage_report

    def _save_report(self, report: Dict, output_path: str):
        """保存报告到JSON文件"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"报告已保存到: {output_path}")

    def print_summary(self, report: Dict):
        """打印验证摘要"""
        print("\n" + "="*60)
        print("数据验证摘要")
        print("="*60)

        print(f"\n总记录数: {report['total_records']}")

        print("\n字段完整性:")
        for field, stats in report['completeness'].items():
            status_icon = "✓" if stats['status'] == 'PASS' else "✗"
            print(f"  {status_icon} {field}: 缺失率 {stats['missing_rate']}%")

        print("\n覆盖率统计:")
        coverage = report['coverage']
        if 'error' not in coverage:
            total_bdcs = len(coverage)
            full_coverage = sum(1 for v in coverage.values() if v['coverage_rate'] == 100)
            print(f"  完全覆盖的BDC: {full_coverage}/{total_bdcs}")
            print(f"  平均覆盖率: {sum(v['coverage_rate'] for v in coverage.values()) / total_bdcs:.2f}%")

        print("\n异常值:")
        anomalies = report['anomalies']
        for anomaly_type, stats in anomalies.items():
            print(f"  {anomaly_type}: {stats['count']} 条")

        print("\n" + "="*60)


if __name__ == "__main__":
    # 使用示例
    validator = DataValidator()
    report = validator.validate_data()
    validator.print_summary(report)
