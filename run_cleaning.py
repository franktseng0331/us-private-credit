"""
数据清洗入口脚本

运行方式:
    python run_cleaning.py              # 标准清洗
    python run_cleaning.py --llm        # 启用 LLM 行业分类（需要 ANTHROPIC_API_KEY）
"""

import argparse
import os
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_cleaner import BDCDataCleaner


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='美国私募信贷 BDC 数据清洗')
    parser.add_argument(
        '--llm',
        action='store_true',
        help='启用 LLM 行业分类补全（需要 ANTHROPIC_API_KEY 环境变量）'
    )
    args = parser.parse_args()

    # 文件路径
    input_csv = 'data/parsed/deal_positions.csv'
    output_csv = 'data/cleaned/deal_positions_clean.csv'
    report_json = 'data/cleaned/cleaning_report.json'

    # 检查输入文件
    if not os.path.exists(input_csv):
        print(f"错误: 输入文件不存在 - {input_csv}")
        sys.exit(1)

    # 检查 LLM 所需的 API key
    if args.llm and not os.environ.get('ANTHROPIC_API_KEY'):
        print("错误: --llm 需要设置 ANTHROPIC_API_KEY 环境变量")
        sys.exit(1)

    # 创建输出目录
    os.makedirs('data/cleaned', exist_ok=True)

    print("=" * 80)
    print("美国私募信贷 BDC 数据清洗")
    if args.llm:
        print("（LLM 行业分类补全已启用）")
    print("=" * 80)

    # 初始化清洗器
    cleaner = BDCDataCleaner(input_csv)

    # 执行清洗流程
    try:
        cleaner.load_data()
        cleaner.step0_dedup()
        cleaner.step1_standardize_investment_type()
        cleaner.step2_clean_industry()
        cleaner.step3_normalize_units()
        cleaner.step4_flag_negative_values()
        cleaner.step5_standardize_dates()
        cleaner.step6_extract_interest_rates()
        cleaner.step7_standardize_borrower_name()
        cleaner.step2_backfill_industry()
        if args.llm:
            cleaner.step_llm_industry()
        cleaner.save_results(output_csv, report_json)

        print("\n" + "=" * 80)
        print("清洗完成!")
        print("=" * 80)
        print(f"输出文件: {output_csv}")
        print(f"清洗报告: {report_json}")

    except Exception as e:
        print(f"\n错误: 清洗过程中出现异常 - {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
