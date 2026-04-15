#!/usr/bin/env python3
"""
US Private Credit Data Collection - Main Execution Script
爬取SEC EDGAR中BDC的Schedule of Investments数据
"""

import os
import json
import pandas as pd
from pathlib import Path
from src.bdc_collector import BDCCollector
from src.simple_parser import SimpleParser
from src.data_validator import DataValidator


def main():
    """主执行流程"""

    # 配置路径
    project_root = Path(__file__).parent
    config_path = project_root / "config" / "bdc_ciks.json"
    raw_data_dir = project_root / "data" / "raw"
    parsed_data_dir = project_root / "data" / "parsed"

    # 确保目录存在
    parsed_data_dir.mkdir(parents=True, exist_ok=True)

    # 设置User-Agent（请替换为你的信息）
    user_agent = "Frank frank@chituedu.com"

    print("=" * 60)
    print("US Private Credit Data Collection")
    print("=" * 60)

    # 步骤1：下载BDC申报文件
    print("\n[步骤1] 下载BDC申报文件...")
    collector = BDCCollector(
        config_path=str(config_path),
        raw_data_dir=str(raw_data_dir),
        user_agent=user_agent
    )

    # 下载10-Q文件（2021-2025）
    filing_types = ["10-Q"]
    collector.download_all_bdcs(
        filing_types=filing_types,
        start_date="2021-01-01",
        end_date="2025-12-31"
    )

    # 步骤2：解析申报文件
    print("\n[步骤2] 解析申报文件...")
    parser = SimpleParser()

    all_records = []

    # 遍历所有下载的文件（直接在raw目录下）
    for cik_dir in raw_data_dir.iterdir():
        if not cik_dir.is_dir():
            continue

        cik = cik_dir.name
        print(f"\n处理 CIK: {cik}")

        for quarter_dir in cik_dir.iterdir():
            if not quarter_dir.is_dir():
                continue

            quarter = quarter_dir.name
            print(f"  - {quarter}")

            # 读取metadata
            metadata_path = quarter_dir / "metadata.json"
            if not metadata_path.exists():
                print(f"    警告: 缺少metadata.json")
                continue

            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            # 使用SimpleParser解析
            try:
                records = parser.parse_filing(str(quarter_dir))
                if records:
                    all_records.extend(records)
                    print(f"    ✓ 解析成功: {len(records)}条记录")
                else:
                    print(f"    × 解析失败: 未找到数据")
            except Exception as e:
                print(f"    × 解析失败: {e}")

    # 步骤3：保存解析结果
    print(f"\n[步骤3] 保存解析结果...")
    if all_records:
        df = pd.DataFrame(all_records)
        output_path = parsed_data_dir / "deal_positions.csv"
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"✓ 已保存 {len(all_records)} 条记录到: {output_path}")
    else:
        print("× 警告: 没有解析到任何数据")
        return

    # 步骤4：数据验证
    print(f"\n[步骤4] 数据质量验证...")
    validator = DataValidator(
        data_path=str(parsed_data_dir / "deal_positions.csv"),
        config_path=str(config_path)
    )

    report = validator.validate_data()
    validator.print_summary(report)

    print("\n" + "=" * 60)
    print("数据收集完成！")
    print("=" * 60)
    print(f"\n主数据文件: {parsed_data_dir / 'deal_positions.csv'}")
    print(f"质量报告: {parsed_data_dir / 'quality_report.json'}")
    print(f"覆盖率报告: {parsed_data_dir / 'coverage_report.json'}")


if __name__ == "__main__":
    main()
