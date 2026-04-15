#!/usr/bin/env python3
"""
测试脚本：下载并解析单个BDC的最新申报文件
用于验证爬虫和解析器是否正常工作
"""

import os
import json
import pandas as pd
from pathlib import Path
from src.bdc_collector import BDCCollector
from src.simple_parser import SimpleParser


def test_single_bdc():
    """测试单个BDC的下载和解析流程"""

    # 配置
    project_root = Path(__file__).parent
    config_path = project_root / "config" / "bdc_ciks.json"
    raw_data_dir = project_root / "data" / "raw"
    parsed_data_dir = project_root / "data" / "parsed"

    # 确保目录存在
    parsed_data_dir.mkdir(parents=True, exist_ok=True)

    # 设置User-Agent（请替换为你的信息）
    user_agent = "PrivateCreditResearch research@example.com"

    print("=" * 60)
    print("测试单个BDC数据爬取")
    print("=" * 60)

    # 测试ARCC（最大的BDC）
    test_ticker = "ARCC"
    test_cik = "1287750"

    print(f"\n[测试目标] {test_ticker} - Ares Capital Corporation")
    print(f"CIK: {test_cik}")

    # 步骤1：下载最新的10-Q文件
    print("\n[步骤1] 下载最新10-Q文件...")
    collector = BDCCollector(
        config_path=str(config_path),
        raw_data_dir=str(raw_data_dir),
        user_agent=user_agent
    )

    try:
        result = collector.download_filing(
            cik=test_cik,
            ticker=test_ticker,
            filing_type="10-Q",
            max_retries=3
        )

        if result:
            print(f"✓ 下载成功")
            print(f"  - 申报日期: {result['filing_date']}")
            print(f"  - 报告期间: {result['period_of_report']}")
            print(f"  - 保存路径: {result['save_path']}")
        else:
            print("× 下载失败")
            return

    except Exception as e:
        print(f"× 下载出错: {e}")
        return

    # 步骤2：解析文件
    print("\n[步骤2] 解析Schedule of Investments...")

    filing_dir = Path(result['save_path'])
    parser = SimpleParser()

    records = []

    # 解析投资数据
    try:
        records = parser.parse_filing(str(filing_dir))
        if records:
            print(f"✓ 解析成功: {len(records)}条记录")
        else:
            print("× 解析失败: 未找到数据")
    except Exception as e:
        print(f"× 解析出错: {e}")
        import traceback
        traceback.print_exc()

    # 步骤3：显示样本数据
    if records:
        print("\n[步骤3] 数据样本预览...")
        df = pd.DataFrame(records)

        print(f"\n总记录数: {len(df)}")
        print(f"字段数: {len(df.columns)}")
        print(f"\n字段列表:")
        for col in df.columns:
            print(f"  - {col}")

        print(f"\n前3条记录:")
        print(df.head(3).to_string())

        # 保存测试结果
        test_output = parsed_data_dir / f"test_{test_ticker}.csv"
        df.to_csv(test_output, index=False, encoding='utf-8-sig')
        print(f"\n✓ 测试数据已保存到: {test_output}")

        # 数据质量检查
        print("\n[步骤4] 数据质量检查...")
        required_fields = ['cik', 'bdc_name', 'ticker', 'filing_date',
                          'borrower_name', 'fair_value_usd_mn']

        for field in required_fields:
            if field in df.columns:
                missing = df[field].isna().sum()
                missing_pct = (missing / len(df)) * 100
                status = "✓" if missing_pct < 5 else "×"
                print(f"  {status} {field}: {missing_pct:.1f}% 缺失")
            else:
                print(f"  × {field}: 字段不存在")

        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)

    else:
        print("\n× 测试失败: 未能解析到任何数据")


if __name__ == "__main__":
    test_single_bdc()
