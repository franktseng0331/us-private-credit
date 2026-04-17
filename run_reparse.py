"""
重新解析 HTML 文件脚本（不重新下载）
v1.4: 修复 simple_parser.py 后，重新解析所有 raw HTML 文件以捕获 FV=0 的 Revolver/DD 行

运行方式:
    python run_reparse.py
"""

import json
import sys
import pandas as pd
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from simple_parser import SimpleParser


def main():
    project_root = Path(__file__).parent
    raw_data_dir = project_root / "data" / "raw"
    parsed_data_dir = project_root / "data" / "parsed"
    parsed_data_dir.mkdir(parents=True, exist_ok=True)

    output_path = parsed_data_dir / "deal_positions.csv"

    print("=" * 70)
    print("BDC HTML 重新解析 (v1.4 — 允许 FV=0 的 Revolver/DD 行)")
    print("=" * 70)

    parser = SimpleParser()
    all_records = []
    filing_count = 0
    error_count = 0

    for cik_dir in sorted(raw_data_dir.iterdir()):
        if not cik_dir.is_dir():
            continue

        cik = cik_dir.name

        for quarter_dir in sorted(cik_dir.iterdir()):
            if not quarter_dir.is_dir():
                continue

            metadata_path = quarter_dir / "metadata.json"
            if not metadata_path.exists():
                continue

            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            ticker = metadata.get('ticker', cik)
            quarter = quarter_dir.name

            try:
                records = parser.parse_filing(str(quarter_dir))
                filing_count += 1
                if records:
                    all_records.extend(records)
                    print(f"  ✓ {ticker} {quarter}: {len(records):,} 条")
                else:
                    print(f"  - {ticker} {quarter}: 0 条（无表格）")
            except Exception as e:
                error_count += 1
                print(f"  ✗ {ticker} {quarter}: 错误 — {e}")

    print(f"\n{'=' * 70}")
    print(f"解析完成：{filing_count} 个 filing，{error_count} 个错误")
    print(f"总记录数：{len(all_records):,}")

    if all_records:
        df = pd.DataFrame(all_records)

        # 统计 FV=0 记录数（新增的 unfunded revolver 行）
        fv_zero = (df['fair_value_usd_mn'] == 0).sum()
        print(f"FV=0 记录数（新增 unfunded revolver/DD）：{fv_zero:,}")

        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"已保存到: {output_path}")
    else:
        print("警告: 未解析到任何数据")
        sys.exit(1)

    print(f"\n下一步: python run_cleaning.py")


if __name__ == '__main__':
    main()
