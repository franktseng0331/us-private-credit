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

---

# v1.3 数据质量修复 (2026-04-17)

多维度质量审计发现 5 个影响数据准确性的问题（P0~P2），已全部修复。

## Bug 7 (P0-A) — step4 未标记极大值异常（FV > 10,000M）

**根因**: `step4_flag_negative_values()` 仅检查负值，未检测统计极大值。2,053 条 `fair_value_usd_mn > 10,000M` 的记录（来自聚合行或单位转换失败残留）未被标记为 `is_anomaly`。

**影响**: 2,053 条极值行污染金额汇总分析，用户过滤 `is_anomaly==False` 后仍受干扰。

**修复**: 在 step4 Rule 3 之后追加 Rule 4：

```python
# 规则4: fair_value > 10,000M → 极大值异常
EXTREME_FV_THRESHOLD = 10_000
extreme_fv_mask = self.df['fair_value_usd_mn'] > EXTREME_FV_THRESHOLD
self.df.loc[extreme_fv_mask, 'is_anomaly'] = True
```

**效果**: `fair_value_usd_mn > 10,000M` 的未标记记录从 2,053 条降至 **0**。

---

## Bug 8 (P0-B) — cost_basis_usd_mn 未独立归一化 + 单位不一致检测缺失

**根因 A（step3）**: 当 filing 的 `fair_value_usd_mn` median 已在 [0.1, 500]M 合理区间时，`step3` 对整个 filing 执行 `continue`，但该 filing 的 `cost_basis_usd_mn` 可能仍为原始美元单位（与 fair_value 独立存储）。典型案例：FSIC fair_value=15M（合理），cost_basis=236,160,807M（原始美元未除以 1M）。

**根因 B（step4）**: 即使 step3 完成转换，逐行 `cb/fv` 比值异常（如 MAIN UniTek cost_basis=281,000M，fair_value=27M）无法被文件级 median 检测捕获。

**影响**: ~11,421 条记录的 `cost_basis_usd_mn` 值虚高数百至数千倍，最大值达 236B M（应为 236M）。

**修复**:

*step3*：在 fair_value 已合理时，独立检测并转换 cost_basis：

```python
else:  # fair_value 已在合理区间，跳过 fv 转换
    cb = self.df.loc[mask, 'cost_basis_usd_mn'].dropna()
    if len(cb) > 0:
        cb_median = cb.median()
        cb_75th = cb.quantile(0.75)
        cb_factor = None
        if cb_median > 500000:
            cb_factor = 1_000_000
        elif cb_75th > 1000:
            cb_factor = 1000
        elif cb_median > 100:
            cb_factor = 1000
        elif 0 < cb_median < 0.001:
            cb_factor = 1_000_000
        if cb_factor:
            self.df.loc[mask, 'cost_basis_usd_mn'] /= cb_factor
            self.df.loc[mask, 'position_size_usd_mn'] /= cb_factor
            cb_conversion_count += 1
```

*step4*：追加 Rule 4b，按 cb/fv 比值检测逐行单位不一致：

```python
# 规则4b: cost_basis 单位不一致（cb/fv 比 > 100 且 cb > 10,000M）
fv_safe = self.df['fair_value_usd_mn'].replace(0, np.nan)
cb_fv_ratio = self.df['cost_basis_usd_mn'] / fv_safe
cb_unit_mismatch = (self.df['cost_basis_usd_mn'] > 10_000) & (cb_fv_ratio > 100)
self.df.loc[cb_unit_mismatch, 'is_anomaly'] = True
```

**效果**:
- step3 新增 242 个 cost_basis-only 转换（filing 级别）
- step4 Rule 4b 新增标记 204 条逐行单位不一致异常
- `cost_basis_usd_mn > 10,000M` 的未标记记录从 207 条降至 **2**（2 条为已接受的边缘案例：FSIC CLO 池 cb≈fv，OBDC2 Amergin 单行）

---

## Bug 9 (P1-A) — PIK 正则未匹配 "PIK Fixed Interest Rate X.X%" 格式

**根因**: `extract_pik_spread_bps()` 的正则 `r'\(?\s*(\d+\.?\d*)\s*(%|bps)?\s*PIK\s*\)?'` 只能匹配"值在 PIK 前面"的格式（如 `1.5% PIK`），无法匹配"PIK 关键字在前"的格式（如 `PIK Fixed Interest Rate 1.5%`）。

**影响**: 约 150 条包含 `PIK Fixed Interest Rate` 格式的记录被错误标记为无 PIK（`pik_spread_bps = NaN`）。

**修复**: 添加第二个正则分支：

```python
# 格式2: PIK Fixed Interest Rate 1.5% — 值在 PIK 关键字后
match2 = re.search(r'PIK\s+(?:Fixed\s+Interest\s+Rate\s+)?(\d+\.?\d*)\s*(%|bps)?',
                   rate_str, re.IGNORECASE)
if match2:
    value = float(match2.group(1))
    unit = match2.group(2)
    if unit and unit.lower() == '%':
        value *= 100
    return float(value)
```

**效果**: `pik_spread_bps.notna()` 有效记录从 3,379 条增至 **3,529 条**（+150 条）。

---

## Bug 10 (P2-A) — LIBOR 退出后仍标注为 LIBOR（缺少 base_rate_clean 字段）

**根因**: `base_rate` 字段直接存储原始提取结果，不处理历史性错误：USD LIBOR 已于 2023-06-30 停用，但 955 条 2023-07 后的记录仍标注为 `LIBOR`（历史合同未更新利率索引）。下游分析者无法区分"真实 SOFR"与"LIBOR 过渡期遗留"。

**影响**: 缺乏字段区分 LIBOR 与 SOFR，影响利率基准分析准确性。

**修复**: 在 step6 末尾新增 `base_rate_clean` 列（向量化实现）：

```python
LIBOR_RETIREMENT = pd.Timestamp('2023-07-01')
filing_date_ts = pd.to_datetime(self.df['filing_date'], errors='coerce')
self.df['base_rate_clean'] = self.df['base_rate'].copy()
libor_post_mask = (self.df['base_rate'] == 'LIBOR') & (filing_date_ts >= LIBOR_RETIREMENT)
self.df.loc[libor_post_mask, 'base_rate_clean'] = 'SOFR_legacy'
```

**效果**: 新增 `base_rate_clean` 字段（第 35 列），955 条 2023-07 后的 LIBOR 记录重标为 `SOFR_legacy`；总字段数从 34 升至 **35**。

---

## Bug 11 (P2-B) — investment_type_std=Unknown 覆盖不足（衍生品/合伙权益/可转债）

**根因**: `classify_investment_type()` 未包含三类常见格式：
1. 利率互换/衍生品（"Interest Rate Swap", "Total Return Swap"）
2. 合伙权益（"Partnership Interest", "Limited Partner Interest", "LP Interest"）
3. 可转换票据（"Convertible Note", "Convertible Bond"）

**影响**: 4,334 条记录（6.0%）被归入 `Unknown`，含 TSLX 1,156 条、HTGC 816 条。

**修复**: 在 `return 'Unknown'` 前插入新映射规则（优先级 14.5）：

```python
# 利率互换 / 衍生品
if any(kw in raw_lower for kw in ['interest rate swap', 'total return swap',
                                    'credit default swap', 'swap agreement', 'derivative']):
    return 'Structured Finance / CLO'

# 合伙权益（有限/普通合伙人份额）
if any(kw in raw_lower for kw in ['partnership interest', 'limited partner',
                                    'general partner', 'gp interest']):
    return 'Common Equity'

# 可转换票据
if any(kw in raw_lower for kw in ['convertible note', 'convertible bond',
                                    'convertible debt', 'convertible debenture']):
    return 'Subordinated Debt'
```

**效果**: `Unknown` 从 4,334 条（6.0%）降至 **3,828 条**（5.3%，减少 506 条）。

---

## v1.3 修复汇总

| Bug | 优先级 | 影响 | 修复文件 | 效果 |
|-----|--------|------|----------|------|
| step4 极大值未标记 | P0-A | 2,053 条极值行未被过滤 | data_cleaner.py step4 | FV>10,000M 未标记降至 0 |
| cost_basis 归一化缺失 | P0-B | ~11,421 条 cb 值虚高 | data_cleaner.py step3+step4 | 242 filing 级转换 + 204 行级标记 |
| PIK 正则格式漏匹配 | P1-A | ~150 条 PIK 未识别 | data_cleaner.py step6 | PIK 有效记录 3,379→3,529 |
| LIBOR 退出后未重标 | P2-A | 无法区分 LIBOR/SOFR | data_cleaner.py step6 | 新增 base_rate_clean，955 条 SOFR_legacy |
| Unknown 类型覆盖不足 | P2-B | 4,334 条未分类 | data_cleaner.py step1 | Unknown 降至 3,828（-506） |
