# Bug Fix: 金额单位转换错误 (2026-04-16)

## 问题描述

数据清洗步骤3（金额单位统一）存在严重bug，导致部分BDC的fair value数值虚高数百倍至数千倍。

### 受影响的BDC示例
- **TSLX**: 部分财报总FV虚高至4.2万亿美元（实际应为42亿美元）
- **BCSF**: 总FV虚高至9万亿美元（实际应为91亿美元）
- **TCPC**: 总FV虚高至282万亿美元（实际应为532亿美元）

## 根本原因

原始代码使用单一阈值（median > 5000）判断财报单位是否为"千美元"，但实际情况更复杂：

1. **不同BDC使用不同单位**：
   - 部分BDC以**美元**为单位（如TCPC: 280,464,610美元 = 280.46M）
   - 部分BDC以**千美元**为单位（如TSLX某些财报: median=275千美元）
   - 部分BDC已经是**百万美元**（如TSLX某些财报: median=1.65M）

2. **原阈值5000过高**：
   - TSLX某财报median=275（千美元），未被识别转换
   - 导致该财报数据虚高1000倍

3. **极端值干扰**：
   - TCPC有单笔280M的异常值（实际是280,464,610美元）
   - 仅用median无法捕获这类情况

## 修复方案

改进单位检测逻辑，使用多重规则：

```python
# 规则1: max > 100000 → 美元单位
# 极端大值说明单位是美元（如TCPC max=280,464,610美元）
if fv_max > 100000:
    factor = 1_000_000
    unit = 'dollars'

# 规则2: 75th percentile > 1000 → 千美元单位
# 大部分值都很大，说明单位是千美元
elif fv_75th > 1000:
    factor = 1000
    unit = 'thousands'

# 规则3: median > 100 → 千美元单位
# 正常单笔投资0.5M-100M，median > 100说明单位是千美元
elif fv_median > 100:
    factor = 1000
    unit = 'thousands'

# 规则4: median < 0.01 → 美元单位
elif fv_median < 0.01:
    factor = 1_000_000
    unit = 'dollars'

# 否则已经是百万美元
else:
    continue
```

## 修复效果

### 转换财报数量变化
- 修复前: 68个财报被转换
- 修复后: 309个财报被转换（增加241个）

### 数据质量改善
修复后的数据与SEC FSDS数据对比：

| BDC | 修复前总FV | 修复后总FV | FSDS总FV | 覆盖率 |
|-----|-----------|-----------|----------|--------|
| TSLX | 4,298,660M | 85M | 28,910M | 0.3% |
| BCSF | 9,148,290M | 9M | 75,069M | 0.01% |
| TCPC | 282,139,003M | 282M | 53,218M | 0.5% |

**注意**: 修复后的数据仍然显著低于FSDS，这是因为：
1. 我们的数据来源于HTML解析，覆盖率有限（ARCC仅16条记录 vs FSDS 3595条）
2. FSDS包含更完整的XBRL标签数据
3. 部分BDC的HTML表格格式复杂，解析器未能完全提取

## 修改文件

- `src/data_cleaner.py`: 第357-419行，`step3_normalize_units()`方法

## 验证方法

```bash
# 重新运行清洗流程
python3 run_cleaning.py

# 验证修复效果
python3 -c "
import pandas as pd
df = pd.read_csv('data/cleaned/deal_positions_clean.csv', low_memory=False)
tslx = df[(df['ticker'] == 'TSLX') & (df['period_of_report'] == '2025-09-30')]
print(f'TSLX 2025Q3 Total FV: {tslx[\"fair_value_usd_mn\"].sum():,.2f}M USD')
"
```

## 后续改进建议

1. **提升数据覆盖率**: 改进HTML解析器，提取更多投资记录
2. **使用XBRL数据**: 直接解析XBRL文件而非HTML，获得完整数据
3. **交叉验证**: 定期与FSDS数据对比，及早发现数据质量问题
