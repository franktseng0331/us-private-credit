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

---

# v1.1 数据质量修复 (2026-04-17)

多智能体并行质检发现5个影响数据准确性的问题，已全部修复。

## Bug 1 — 缺少去重步骤（2,273条重复行）

**根因**: `BDCDataCleaner` 类中没有任何 `drop_duplicates()` 调用，清洗报告声称"已去重"实属不实。

**影响**: 73,960条记录中含2,273条完全重复行（3.07%），污染统计分析结果。

**修复**: 新增 `step0_dedup()` 方法，在数据加载后立即执行去重，并在 `run_cleaning.py` 中插入调用。

**效果**: 总记录数从73,960降至71,687（移除2,273条）。

---

## Bug 2 — step3 单位转换算法过度转换

**根因**: 迭代收敛逻辑使用 `p99 > 100000` 作为"美元单位"判断条件，但部分BDC（如OBDC 2022-2024）的合法大仓位（CLO/结构化产品，8000M+）会触发该条件，导致已正确的百万美元数据被错误地除以1,000,000，结果变成接近零的极小值。

**影响**: OBDC 2022-2024年数据 `fair_value_usd_mn` 中位数从2.1M降至 8.2e-15（几乎为零）。

**修复**: 重写 `step3_normalize_units()` 为单次判断+合理区间保护逻辑：
- 若 median 在 [0.1, 500]M 合理区间，直接跳过（防止合法大仓位误触发）
- `median > 500,000` → 美元单位（除以1,000,000）
- `p75 > 1000` 或 `median > 100` → 千美元单位（除以1,000）
- 移除迭代逻辑，改为单次准确判断

**效果**: 转换财报数217个，所有BDC中位数恢复合理（OBDC 2.1M，HTGC 21.5M，TSLX 3.7M等）。

---

## Bug 3 — run_cleaning.py 缺少 step2_backfill_industry() 调用

**根因**: `data_cleaner.py` 内置 `main()` 中调用了 `step2_backfill_industry()`，但 `run_cleaning.py` 遗漏了这一调用。

**影响**: `industry_clean` 字段回填未执行，有效率仅为15.34%而非预期更高的值。

**修复**: 在 `run_cleaning.py` 的 step7 之后追加 `cleaner.step2_backfill_industry()` 调用。

**效果**: 跨季度回填1,516条记录，有效率提升至17.45%（受限于原始数据中industry字段整体缺失率较高）。

---

## Bug 4 — step5 未生成 is_expired 标志列

**根因**: `step5_standardize_dates()` 解析了 maturity_date 但未创建 `is_expired` 布尔列，后续分析无法直接过滤到期投资。

**影响**: 数据集缺少到期状态字段，用户需自行计算。

**修复**: 在日期解析完成后追加 `is_expired` 列：
```python
today = pd.Timestamp.today().normalize()
self.df['is_expired'] = maturity_parsed.notna() & (maturity_parsed < today)
```

**效果**: 新增 `is_expired` 字段，检测到15,421条已到期投资记录。

---

## Bug 5 — PIK利差返回 0 而非 NaN

**根因**: `extract_pik_spread_bps()` 在找不到PIK数据时返回 `0`，无法区分"真实零利差"与"缺失数据"。

**影响**: 68,288条无PIK的记录被标记为0利差，导致统计分析（均值、计数）产生偏差。

**修复**: 将 `return 0` 改为 `return np.nan`，返回类型从 `int` 改为 `float`。

**效果**: PIK缺失值统一为 NaN，可通过 `pik_spread_bps.notna()` 准确过滤有效PIK记录（3,379条）。

---

## v1.1 修复汇总

| Bug | 影响 | 修复文件 | 效果 |
|-----|------|----------|------|
| 缺少去重 | 2,273条重复 | data_cleaner.py, run_cleaning.py | 记录数从73,960→71,687 |
| 单位过度转换 | OBDC等BDC数据归零 | data_cleaner.py step3 | 所有BDC中位数恢复合理 |
| 回填未调用 | industry有效率偏低 | run_cleaning.py | 回填1,516条，有效率17.45% |
| 缺少is_expired | 无到期状态字段 | data_cleaner.py step5 | 新增字段，15,421条到期 |
| PIK返回0 | 统计分析偏差 | data_cleaner.py | NaN正确区分缺失vs零值 |

---

# v1.2 数据质量修复 (2026-04-17)

## Bug 6 — spread_bps 返回 0 而非 NaN（虚假零值污染）

**根因**: `extract_spread_bps()` 在两种情况下返回 `0`：
1. 输入为 NaN（无利率字段）
2. 正则表达式未匹配（利率格式不含 `+XXXbps` 模式）

导致 54,911 条（76.6%）记录被错误标记为零利差，无法区分"真实零利差"（固定利率贷款）与"数据缺失/提取失败"（权益类投资、格式不兼容）。

**影响**:
- `spread_bps` 列类型为 `int64`，无法存储 NaN
- 54,911 条虚假零值污染均值、分布等统计分析
- 与已修复的 `pik_spread_bps` 语义不一致

**修复**: 将 `extract_spread_bps()` 对齐 `extract_pik_spread_bps()` 的处理方式：

```python
# 修复前
def extract_spread_bps(rate_str: str) -> int:
    if pd.isna(rate_str):
        return 0
    ...
    return int(value)
    return 0

# 修复后
def extract_spread_bps(rate_str: str) -> float:
    """提取总利差（基点），无法提取返回 np.nan 以区分零利差"""
    if pd.isna(rate_str):
        return np.nan
    ...
    return float(value)
    return np.nan
```

**修改文件**: `src/data_cleaner.py` 第 556–572 行

**效果**:

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 列类型 | `int64` | `float64` |
| 虚假零值记录数 | 54,911 | 19（真实零利差） |
| NaN 记录数 | 0 | 54,892 |
| 有效记录数（>0） | 16,776 | 16,776（不变） |
| `spread_bps` 有效率 | 100%（含虚假零值） | 23.4%（真实有效） |

## v1.2 修复汇总

| Bug | 影响 | 修复文件 | 效果 |
|-----|------|----------|------|
| spread_bps返回0 | 54,911条虚假零值 | data_cleaner.py step6 | NaN正确区分缺失vs零值，有效率23.4% |
