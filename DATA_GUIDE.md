# US Private Credit BDC Dataset — 数据说明报告

**版本**: v1.3  
**生成日期**: 2026-04-17  
**数据集**: `data/cleaned/deal_positions_clean.csv`  
**作者**: Fan Zeng

---

## 目录

1. [数据集概览](#1-数据集概览)
2. [数据来源与采集方法](#2-数据来源与采集方法)
3. [清洗流程说明](#3-清洗流程说明)
4. [字段说明（35个）](#4-字段说明)
5. [数据分布详情](#5-数据分布详情)
   - 5.1 BDC覆盖列表
   - 5.2 时间维度分布
   - 5.3 投资类型分布
   - 5.4 行业分布
   - 5.5 公允价值分布
   - 5.6 利率与利差
   - 5.7 到期日分析
6. [数据质量说明](#6-数据质量说明)
   - 6.1 字段完整性
   - 6.2 异常标记体系
   - 6.3 已知局限性
7. [使用指南](#7-使用指南)
   - 7.1 推荐过滤方法
   - 7.2 典型分析场景
   - 7.3 代码示例
8. [附录：BDC完整列表](#8-附录bdc完整列表)

---

## 1. 数据集概览

本数据集收集了美国 **39 家**商业发展公司（Business Development Companies，BDC）在 SEC EDGAR 系统提交的季度投资组合报告（Form N-PORT / 10-Q / 10-K），涵盖 **2020年Q4 至 2025年Q4** 共 21 个季度，包含 **71,687 条**投资持仓明细记录。

### 关键统计速览

| 指标 | 数值 |
|------|------|
| **总记录数** | 71,687 条 |
| **有效记录数**（排除异常）| 68,230 条 |
| **BDC 数量** | 39 家 |
| **报告期数量** | 491 个 |
| **时间跨度** | 2020-Q4 至 2025-Q4 |
| **唯一借款人数**（标准化后）| 7,726 家 |
| **字段数** | 35 个 |
| **文件大小** | ~29 MB（CSV）|
| **数据版本** | v1.3 |

### 有效记录金额汇总（排除 is_anomaly=True）

| 统计项 | 金额 |
|--------|------|
| **债权投资总公允价值** | ~5,818.6 亿美元 |
| **权益投资总公允价值** | ~2,911.1 亿美元 |
| **单笔投资中位数** | 2.90M 美元 |
| **单笔投资均值** | 135.3M 美元（受CLO大仓位影响）|
| **单笔投资 P95** | 167M 美元 |

> **注意**：均值受部分 CLO / 合并仓位的超大值影响，建议使用中位数评估"典型单笔投资规模"。

---

## 2. 数据来源与采集方法

### 2.1 原始数据来源

- **监管机构**: 美国证券交易委员会（SEC）EDGAR 系统
- **报告类型**: Form N-PORT（月度）、Form 10-Q（季度）、Form 10-K（年度）
- **解析格式**: HTML 表格（Schedule of Investments 部分）
- **时间范围**: 2021-01-06 至 2026-02-27（报告提交日期）

### 2.2 采集说明

使用 Python 脚本从 EDGAR 下载并解析各 BDC 的 HTML 格式投资组合附表，提取每笔投资的借款人名称、投资类型、公允价值、成本基础、到期日、利率等字段。

**filing_type 分布**：

| 类型 | 记录数 | 说明 |
|------|--------|------|
| 10-Q | 69,889（97.5%）| 季度报告（主体） |
| 10-K | 1,798（2.5%）| 年度报告 |

### 2.3 数据局限性（重要）

1. **仅解析 HTML 格式**：未包含 XBRL 格式数据，XBRL 通常更完整（如 ARCC 实际持仓 3,595 条，本数据集仅 90 条）。
2. **聚合行混入**：部分 BDC 原始文件将"Senior Secured Loans 合计"等汇总行混入明细数据，产生极大异常值（已通过 `is_anomaly` 标记）。
3. **BDC 覆盖不均**：部分 BDC 数据稀少（如 GDLC 仅 6 条、SLRC 仅 15 条），不适合单独分析。
4. **行业字段缺失率高**：SEC N-PORT 原始表格中 industry 字段普遍缺失，`industry_clean` 有效率仅 17.5%。

---

## 3. 清洗流程说明

### 3.1 九步清洗管道

| 步骤 | 方法 | 操作说明 |
|------|------|---------|
| **Step 0** | `step0_dedup()` | 去除完全重复行（移除 2,273 条） |
| **Step 1** | `step1_standardize_investment_type()` | 统一投资类型命名（14 类标准化类型） |
| **Step 2** | `step2_clean_industry()` | 行业字段清洗 + GICS 标签映射 |
| **Step 3** | `step3_normalize_units()` | 将所有金额统一为百万美元（M USD） |
| **Step 4** | `step4_flag_negative_values()` | 负值标记 + 极大值异常标记 |
| **Step 5** | `step5_standardize_dates()` | 解析到期日并生成 `is_expired` 字段 |
| **Step 6** | `step6_extract_interest_rates()` | 提取基准利率、利差、PIK 利差，新增 `base_rate_clean` |
| **Step 7** | `step7_standardize_borrower_name()` | 标准化借款人名称（减少别名差异）|
| **Step 2b** | `step2_backfill_industry()` | 跨季度回填行业标签（+1,516 条） |

### 3.2 关键清洗逻辑

#### 单位归一化（Step 3）

不同 BDC 使用不同报告单位（美元、千美元、百万美元），采用以下单次判断逻辑：

```
若 median 在 [0.1, 500]M → 已是百万美元，跳过
若 median > 500,000       → 美元单位，除以 1,000,000
若 P75 > 1,000 或 median > 100 → 千美元单位，除以 1,000
若 median < 0.001         → 美元单位，除以 1,000,000
```

- fair_value 转换：217 个 filing
- cost_basis 独立转换（fair_value 已合理但 cost_basis 仍为原始单位）：242 个 filing

#### 异常标记（Step 4）

| 规则 | 条件 | 标记字段 |
|------|------|---------|
| Rule 1 | `fair_value_usd_mn < 0` | `is_anomaly = True` |
| Rule 2 | `cost_basis_usd_mn < 0`（非 Revolver） | `is_anomaly = True` |
| Rule 3 | `is_unfunded_liability`（Revolver 未提款） | `is_unfunded_liability = True` |
| Rule 4 | `fair_value_usd_mn > 10,000M`（聚合行/转换失败）| `is_anomaly = True` |
| Rule 4b | `cost_basis_usd_mn > 10,000M` AND `cb/fv > 100`（单位不一致）| `is_anomaly = True` |

---

## 4. 字段说明

数据集共 **35 个字段**，分为以下几类：

### 4.1 标识字段

| 字段名 | 类型 | 非空率 | 说明 |
|--------|------|--------|------|
| `cik` | int64 | 100% | SEC 中央索引键，BDC 的唯一监管标识符 |
| `ticker` | str | 100% | BDC 股票代码（如 ARCC、TSLX） |
| `bdc_name` | str | 100% | BDC 全称 |
| `filing_id` | str | 100% | 单份报告的唯一标识（格式：`{ticker}_{period}`） |
| `filing_type` | str | 100% | 报告类型（10-Q 或 10-K） |
| `data_source` | str | 100% | 数据来源格式（当前均为 HTML） |
| `is_amended` | bool | 100% | 是否为修正报告（当前数据集均为 False） |
| `raw_row` | str | 100% | 原始 HTML 表格行内容（用于追溯验证） |

### 4.2 时间字段

| 字段名 | 类型 | 非空率 | 说明 |
|--------|------|--------|------|
| `filing_date` | datetime | 100% | 报告提交 SEC 的日期 |
| `period_of_report` | str | 100% | 报告所属期末日期（如 2025-09-30） |
| `quarter` | str | 100% | 报告季度（格式：`YYYY-QN`，如 2025-Q3） |
| `maturity_date` | str | 76.5% | 标准化后的到期日（YYYY-MM-DD） |
| `maturity_raw` | str | 77.5% | 原始到期日字符串 |

### 4.3 借款人字段

| 字段名 | 类型 | 非空率 | 说明 |
|--------|------|--------|------|
| `borrower_name` | str | 100% | 原始借款人/被投资企业名称 |
| `borrower_name_clean` | str | 100% | 标准化后的借款人名称（去除法律形式后缀、大写统一等） |

### 4.4 投资分类字段

| 字段名 | 类型 | 非空率 | 说明 |
|--------|------|--------|------|
| `investment_type` | str | 100% | 原始投资类型字符串 |
| `investment_type_std` | str | 100% | 标准化投资类型（14 类，见 §5.3） |
| `seniority` | str | 74.6% | 债权优先级（First Lien / Second Lien / Senior / Subordinated 等） |
| `industry` | str | 38.1% | 原始行业字段 |
| `industry_clean` | str | 17.5% | 清洗后行业标签（GICS 子行业级别，跨季度回填后） |
| `industry_gics` | str | 100% | 粗粒度 GICS 行业分类（11 类 + Unknown） |

> **说明**：`industry_gics` 对所有记录均有值，但 82.6% 为 "Other / Unknown"（原始数据行业字段缺失所致）。`industry_clean` 仅 17.5% 有效，建议在行业分析时注意样本偏差。

### 4.5 金额字段

| 字段名 | 类型 | 非空率 | 说明 |
|--------|------|--------|------|
| `fair_value_raw` | str | 100% | 原始公允价值字符串（用于追溯） |
| `fair_value_usd_mn` | float64 | 100% | **公允价值（百万美元）**，核心分析字段 |
| `cost_basis_usd_mn` | float64 | 98.8% | 成本基础（百万美元，含摊余成本） |
| `position_size_usd_mn` | float64 | 89.6% | 仓位面值/名义金额（百万美元）|

> **重要**：分析金额时请先过滤 `is_anomaly == False`，否则均值受极大聚合行污染（含异常时均值约 3.1 万 M，排除后约 135 M）。

### 4.6 利率字段

| 字段名 | 类型 | 非空率 | 说明 |
|--------|------|--------|------|
| `interest_rate_raw` | str | 64.8% | 原始利率字符串（如 "SOFR + 650 bps"） |
| `base_rate` | str | 56.9% | 提取的基准利率（SOFR / LIBOR / Fixed / PRIME 等） |
| `base_rate_clean` | str | 56.9% | **清洗后基准利率**：2023-07-01 后的 LIBOR 重标为 SOFR_legacy |
| `spread_raw` | str | 26.6% | 原始利差字符串 |
| `spread_bps` | float64 | 23.4% | **提取的浮动利差（基点）**，NaN 表示固定利率或提取失败 |
| `pik_spread_bps` | float64 | 4.9% | **PIK 利差（基点）**，NaN 表示无 PIK 条款 |
| `is_pik` | bool | 100% | 是否含 PIK（Payment-in-Kind）条款 |

> **NaN 语义说明**：
> - `spread_bps = NaN`：该投资可能为固定利率、权益类或格式无法解析，**不代表零利差**。
> - `pik_spread_bps = NaN`：该投资无 PIK 条款，**不代表 PIK 利差为零**。
> - `is_pik = True` 但 `pik_spread_bps = NaN`：PIK 条款存在但具体利率未能提取。

### 4.7 状态标记字段

| 字段名 | 类型 | 非空率 | 说明 |
|--------|------|--------|------|
| `is_anomaly` | bool | 100% | **异常记录标记**（共 3,457 条）：含负值、极大值、CB单位不一致 |
| `is_unfunded_liability` | bool | 100% | 未提款承诺（Revolver/Delayed Draw，公允价值为负）|
| `is_expired` | bool | 100% | 是否已到期（maturity_date < 今日，共 15,421 条）|

---

## 5. 数据分布详情

### 5.1 BDC 覆盖列表

数据集覆盖 **39 家**美国上市 BDC，按记录数降序：

| 排名 | Ticker | 记录数 | 报告期 | 有效FV合计 |
|------|--------|--------|--------|-----------|
| 1 | OCSL | 8,943 | 15 | 85.1亿美元 |
| 2 | BCSF | 8,181 | 10 | 106.4亿美元 |
| 3 | TRIN | 7,189 | 15 | 897.4亿美元 |
| 4 | PSEC | 5,866 | 17 | 3,530.2亿美元 |
| 5 | MAIN | 4,267 | 16 | 30.0亿美元 |
| 6 | CSWC | 3,369 | 15 | 14.9亿美元 |
| 7 | TPVG | 3,072 | 15 | 17.9亿美元 |
| 8 | PTMN | 2,932 | 14 | 11.9亿美元 |
| 9 | MFIC | 2,873 | 11 | 341.4亿美元 |
| 10 | SCM | 2,794 | 14 | 103.6亿美元 |
| 11 | TSLX | 2,786 | 16 | 61.5亿美元 |
| 12 | FSIC | 2,716 | 16 | 338.9亿美元 |
| 13 | OFS | 2,287 | 15 | 177.1亿美元 |
| 14 | OBDC | 2,085 | 15 | 955.8亿美元 |
| 15 | MSIF | 1,914 | 12 | 4.4亿美元 |
| ... | 其余 24 家 | — | — | — |

> **注意**：记录数多≠资产规模大。BCSF 记录数 8,181 但总 FV 仅 106 亿美元；PSEC 记录数 5,866 但总 FV 达 3,530 亿美元（持有大量小型仓位）。部分 BDC（ARCC、GBDC、SLRC 等）因 HTML 解析覆盖不完整，记录数与实际规模严重不符。

### 5.2 时间维度分布

#### 按年分布

| 年份 | 记录数 | BDC 数 | 报告期数 |
|------|--------|--------|--------|
| 2021 | 7,730 | 30 | 6 |
| 2022 | 10,859 | 35 | 7 |
| 2023 | 15,600 | 37 | 6 |
| 2024 | 16,054 | 36 | 6 |
| 2025 | 19,329 | 35 | 7 |
| 2026 | 2,115 | 8 | 1 |

数据从 2021 年至 2025 年稳步增长，2025 年记录数最多（19,329 条）。2026 年仅含 2025-Q4 报告（提交于 2026 年初）。

#### 按季度分布（近四年）

| 季度 | 记录数 | 利差中位数 |
|------|--------|-----------|
| 2022-Q1 | 3,074 | 630 bps |
| 2022-Q3 | 3,336 | 675 bps |
| 2023-Q1 | 4,781 | 650 bps |
| 2023-Q4 | 1,354 | 725 bps |
| 2024-Q1 | 5,184 | 650 bps |
| 2024-Q4 | 1,622 | 750 bps |
| 2025-Q1 | 5,742 | 580 bps |
| 2025-Q3 | 5,827 | 580 bps |

> Q4 记录数偏少（如 2023-Q4 仅 1,354）是因为 10-K 提交延迟，部分 BDC 的 Q4 数据在次年 Q1 才被纳入。

### 5.3 投资类型分布

基于标准化字段 `investment_type_std`（共 14 类）：

| 投资类型 | 记录数 | 占比 | 说明 |
|----------|--------|------|------|
| **First Lien Term Loan** | 22,805 | 31.8% | 一级抵押定期贷款（私募信贷核心品类） |
| **Common Equity** | 14,129 | 19.7% | 普通股权（含合伙权益） |
| **Senior Secured Loan** | 10,441 | 14.6% | 高级有担保贷款（含未细分的一级二级） |
| **Preferred Equity** | 6,471 | 9.0% | 优先股 |
| **Warrant** | 4,491 | 6.3% | 认股权证 |
| **Unknown** | 3,828 | 5.3% | 格式无法识别（含部分衍生品） |
| **Second Lien Term Loan** | 2,914 | 4.1% | 二级抵押定期贷款 |
| **First Lien Delayed Draw** | 2,861 | 4.0% | 一级抵押延迟提款（通常为 RCF 未提款部分） |
| **Subordinated Debt** | 1,810 | 2.5% | 次级债（含可转债） |
| **First Lien Revolver** | 813 | 1.1% | 一级抵押循环信贷 |
| **Revolver** | 779 | 1.1% | 循环信贷（未细分优先级） |
| **Structured Finance / CLO** | 273 | 0.4% | 结构化产品 / CLO 股权层 |
| **Unsecured Note** | 66 | 0.1% | 无担保票据 |
| **Unitranche Loan** | 6 | 0.0% | 单一优先贷款 |

**债权 vs 权益分拆**（排除异常记录）：

- 债权类（First Lien / Second Lien / Senior Secured / Sub / Revolver 等）：**41,264 条**，总 FV **5,818.6B 美元**
- 权益类（Common Equity / Preferred / Warrant）：**23,139 条**，总 FV **2,911.1B 美元**

### 5.4 行业分布

#### industry_clean（精细行业，有效率 17.5%）

| 行业 | 记录数 | 占 industry_clean 有效记录比 |
|------|--------|------|
| Application Software | 1,297 | 10.3% |
| Structured Finance | 1,059 | 8.4% |
| Health Care Services | 489 | 3.9% |
| Pharmaceuticals | 469 | 3.7% |
| Health Care Providers & Services | 297 | 2.4% |
| Health Care Technology | 275 | 2.2% |
| Commercial Services & Supplies | 268 | 2.1% |
| Biotechnology | 268 | 2.1% |
| Construction & Engineering | 255 | 2.0% |
| Aerospace & Defense | 233 | 1.8% |

> **注意**：`industry_clean` 的 17.5% 有效率意味着 82.5% 的记录行业未知，使用该字段进行行业分析时存在显著样本偏差。

#### industry_gics（粗粒度，100% 覆盖但 82.6% 为 Unknown）

| GICS 大类 | 记录数 | 占比 |
|-----------|--------|------|
| Software & Technology | 2,754 | 3.8% |
| Industrials | 2,234 | 3.1% |
| Healthcare | 2,033 | 2.8% |
| Consumer | 1,430 | 2.0% |
| Structured Finance | 1,059 | 1.5% |
| Business Services | 904 | 1.3% |
| Financial Services | 885 | 1.2% |
| Media & Telecom | 758 | 1.1% |
| Real Estate | 175 | 0.2% |
| Energy | 157 | 0.2% |
| Education | 104 | 0.1% |
| Other / Unknown | 59,194 | 82.6% |

### 5.5 公允价值分布

#### 分位数分布（排除 is_anomaly=True，68,230 条）

| 分位数 | fair_value_usd_mn |
|--------|-------------------|
| 最小值 | ~0 M |
| P5 | 0.08 M |
| P25（下四分位）| 0.69 M |
| **中位数** | **2.90 M** |
| 均值 | 135.3 M |
| P75（上四分位）| 10.0 M |
| P95 | 167 M |
| **最大值** | 10,000 M（异常阈值边界）|

> 分布高度右偏：75% 的投资低于 10M 美元，但均值被大型 CLO 仓位拉高至 135M。典型私募信贷单笔投资规模在 **1M–30M** 美元区间。

#### 按 BDC 中位数排名（有代表性 BDC）

| BDC | 中位数单笔 FV |
|-----|-------------|
| MRCC | 28.0 M |
| BXSL | 93.0 M（CLO 池） |
| HTGC | 22.7 M |
| FSIC | 12.1 M |
| OBDC | 2.1 M |
| CSWC | 2.0 M |
| TSLX | 3.8 M |
| PSEC | 0.9 M（大量小型仓位）|

### 5.6 利率与利差

#### 基准利率分布（base_rate_clean）

| 基准利率 | 记录数 | 占比 | 说明 |
|----------|--------|------|------|
| SOFR | 18,402 | 25.7% | 担保隔夜融资利率（2022 后主流） |
| Fixed | 8,431 | 11.8% | 固定利率（权益、次级债常见） |
| LIBOR | 8,351 | 11.6% | 旧基准利率（2023-06 前有效） |
| PRIME | 4,670 | 6.5% | 美国优惠利率 |
| **SOFR_legacy** | **955** | **1.3%** | 2023-07-01 后标注为 LIBOR 的合同（v1.3 新增，涉及 20 家 BDC）|
| 未提取 | 30,878 | 43.1% | 权益类或格式无法解析 |

> `SOFR_legacy` 标识的 955 条记录分布在 20 家 BDC，代表 LIBOR 退出过渡期内尚未更新利率索引条款的存量合同。

#### 利差（spread_bps）统计

基于 16,795 条有效记录（23.4%，浮动利率债权投资）：

| 统计项 | 数值 |
|--------|------|
| 最小值 | 0 bps（真实零利差，19 条）|
| P25 | 525 bps |
| **中位数** | **650 bps** |
| 均值 | 645 bps |
| P75 | 775 bps |
| 最大值 | 1,900 bps |

利差中位数在 2020–2025 年区间稳定在 580–750 bps，2023-Q4 和 2024-Q4 出现小幅上升（市场风险溢价扩大）；2025 年有所收窄（约 580 bps）。

#### PIK 利差（pik_spread_bps）统计

基于 3,529 条有效记录（4.9%）：

| 统计项 | 数值 |
|--------|------|
| **中位数** | **700 bps** |
| 均值 | 713 bps |
| 最大值 | 3,000 bps |

#### PIK 利率趋势

| 年份 | 总记录 | PIK 记录 | PIK 占比 |
|------|--------|---------|---------|
| 2021 | 7,730 | 703 | 9.1% |
| 2022 | 10,859 | 888 | 8.2% |
| 2023 | 15,600 | 1,174 | 7.5% |
| 2024 | 16,054 | 1,604 | 10.0% |
| 2025 | 19,329 | 1,818 | 9.4% |

PIK 占比在 2023 年短暂下降后，2024–2025 年重返 9–10%，反映高利率环境下借款人现金利息压力增大、选择 PIK 缓解还款。

### 5.7 到期日分析

#### 基本统计

| 指标 | 数值 |
|------|------|
| 有效到期日记录数 | 25,197 条（35.2%）|
| 已到期（is_expired=True） | 15,421 条（21.5%）|
| 未来到期记录数 | ~9,776 条 |

#### 到期墙（Maturity Wall，2026–2030）

未到期且有效到期日记录，按年汇总：

| 到期年份 | 到期记录数 | 对应总 FV（亿美元）|
|----------|-----------|-----------------|
| 2026 | 1,420 | 49.2 |
| **2027** | **2,301** | **176.9**（近期最大到期墙）|
| 2028 | 2,091 | 125.5 |
| 2029 | 1,931 | 68.0 |
| 2030 | 1,087 | 57.3 |

2027 年形成最大到期集中（176.9 亿美元），是 BDC 投资组合中需关注的再融资压力节点。

---

## 6. 数据质量说明

### 6.1 字段完整性

| 字段 | 非空率 | 备注 |
|------|--------|------|
| `fair_value_usd_mn` | 100% | 核心字段，无缺失 |
| `investment_type_std` | 100% | 已标准化，Unknown 占 5.3% |
| `is_anomaly` | 100% | 布尔标记，完整 |
| `is_pik` | 100% | 布尔标记，完整 |
| `cost_basis_usd_mn` | 98.8% | 约 1.2% 缺失 |
| `position_size_usd_mn` | 89.6% | 约 10% 缺失 |
| `maturity_date` | 76.5% | 权益类通常无到期日 |
| `seniority` | 74.6% | 部分 BDC 未披露 |
| `base_rate` / `base_rate_clean` | 56.9% | 权益类/格式不支持 |
| `interest_rate_raw` | 64.8% | 原始利率字符串 |
| `spread_bps` | 23.4% | 仅浮动利率债权可提取 |
| `industry_clean` | 17.5% | 受原始 N-PORT 缺失率限制 |
| `pik_spread_bps` | 4.9% | 仅 PIK 投资有效 |

### 6.2 异常标记体系

| 类别 | 记录数 | 说明 |
|------|--------|------|
| `is_anomaly = True`（总计）| **3,457** | 需过滤后再分析 |
| — fair_value > 10,000M（极大值）| 2,053 | 聚合行或单位转换失败 |
| — cost_basis 单位不一致（cb/fv > 100）| 204 | 逐行单位错误 |
| — fair_value < 0 | 200 | 含小量负值 |
| `is_unfunded_liability = True` | 0 | 未提款 Revolver（当前版本未检出独立标记）|
| `is_expired = True` | 15,421 | 已到期投资，仍计入持仓（历史记录） |

### 6.3 已知局限性与注意事项

1. **不适合用于单一 BDC 的完整投资组合分析**：
   - ARCC（最大 BDC，实际 AUM >200亿）仅有 90 条记录，严重低于真实持仓数量
   - GBDC、SLRC、GDLC 等数据同样不完整

2. **行业分析需谨慎**：
   - `industry_clean` 仅 17.5% 有效，且已有数据偏向特定 BDC（如覆盖好的 TSLX、CSWC）
   - 使用行业分析结论时应明确说明样本局限

3. **金额分析必须先过滤异常**：
   - 不过滤 `is_anomaly` 时，均值约 3.1 万 M，完全失真
   - 建议使用 `df[~df['is_anomaly']]` 作为基础分析集

4. **到期日覆盖仅 35%**：
   - 权益类投资（Warrant、Common Equity）通常无到期日
   - 到期墙分析仅反映有到期日记录，可能低估实际规模

5. **利差提取率仅 23.4%**：
   - 固定利率投资（`base_rate = Fixed`）无利差
   - 部分 BDC 利率字段格式特殊，正则未能覆盖

---

## 7. 使用指南

### 7.1 推荐过滤方法

```python
import pandas as pd

df = pd.read_csv('deal_positions_clean.csv', low_memory=False)
df['filing_date'] = pd.to_datetime(df['filing_date'])
df['maturity_date'] = pd.to_datetime(df['maturity_date'], errors='coerce')

# ✅ 推荐：基础分析集（排除聚合行/单位错误等异常）
df_base = df[~df['is_anomaly']]

# ✅ 推荐：债权投资分析
debt_types = [
    'First Lien Term Loan', 'Second Lien Term Loan', 'Senior Secured Loan',
    'First Lien Delayed Draw', 'First Lien Revolver', 'Revolver',
    'Subordinated Debt', 'Unsecured Note', 'Unitranche Loan'
]
df_debt = df_base[df_base['investment_type_std'].isin(debt_types)]

# ✅ 推荐：权益投资分析
df_equity = df_base[df_base['investment_type_std'].isin(
    ['Common Equity', 'Preferred Equity', 'Warrant']
)]

# ✅ 推荐：活跃投资（排除已到期）
df_active = df_base[~df_base['is_expired']]

# ✅ 推荐：有利差数据的浮动利率投资
df_floating = df_base[df_base['spread_bps'].notna()]

# ✅ 推荐：PIK 投资筛选
df_pik = df_base[df_base['is_pik'] == True]

# ✅ 推荐：使用 base_rate_clean 区分真正的 SOFR 与过渡期遗留合同
df_sofr = df_base[df_base['base_rate_clean'] == 'SOFR']
df_sofr_legacy = df_base[df_base['base_rate_clean'] == 'SOFR_legacy']
```

### 7.2 典型分析场景

#### 场景 A：市场利差趋势分析

```python
# 按季度统计利差中位数
spread_trend = (
    df_floating
    .groupby('quarter')['spread_bps']
    .agg(['median', 'mean', 'count'])
    .rename(columns={'median': 'bps_median', 'mean': 'bps_mean', 'count': 'n'})
)
print(spread_trend)
```

#### 场景 B：PIK 投资分析

```python
# PIK 投资按年占比趋势
pik_trend = (
    df_base
    .groupby(df_base['filing_date'].dt.year)
    .agg(total=('is_pik', 'count'), pik=('is_pik', 'sum'))
)
pik_trend['pik_pct'] = pik_trend['pik'] / pik_trend['total'] * 100
print(pik_trend)

# PIK 利差分布
pik_spread = df_base[df_base['pik_spread_bps'].notna()]['pik_spread_bps']
print(pik_spread.describe())
```

#### 场景 C：到期墙（Maturity Wall）分析

```python
# 未到期的有效投资，按年汇总到期金额
df_future = df_active[df_active['maturity_date'].notna() & 
                       (df_active['maturity_date'] > pd.Timestamp.today())]
maturity_wall = df_future.groupby(df_future['maturity_date'].dt.year).agg(
    count=('fair_value_usd_mn', 'count'),
    total_fv_B=('fair_value_usd_mn', lambda x: x.sum() / 1000)
)
print(maturity_wall[maturity_wall.index.between(2025, 2030)])
```

#### 场景 D：BDC 投资组合比较

```python
# 各 BDC 的资产类型构成
type_mix = (
    df_base
    .groupby(['ticker', 'investment_type_std'])['fair_value_usd_mn']
    .sum()
    .unstack(fill_value=0)
)
type_mix_pct = type_mix.div(type_mix.sum(axis=1), axis=0) * 100
print(type_mix_pct.round(1))
```

#### 场景 E：LIBOR/SOFR 过渡分析

```python
# 基准利率随时间演变
rate_trend = (
    df_base[df_base['base_rate_clean'].notna()]
    .groupby(['quarter', 'base_rate_clean'])
    .size()
    .unstack(fill_value=0)
)
# SOFR_legacy 标记的合同为 LIBOR 退出后仍未更新索引的存量
legacy = df_base[df_base['base_rate_clean'] == 'SOFR_legacy']
print(f"SOFR_legacy 涉及 {legacy['ticker'].nunique()} 家 BDC")
```

#### 场景 F：借款人共同持有分析（Co-investment）

```python
# 被多个 BDC 共同持有的借款人
co_invest = (
    df_base
    .groupby('borrower_name_clean')['ticker']
    .nunique()
    .sort_values(ascending=False)
)
print("被 3 家以上 BDC 共同持有的借款人:")
print(co_invest[co_invest >= 3].head(20))
```

### 7.3 数据加载完整示例

```python
import pandas as pd
import numpy as np

# 加载数据
df = pd.read_csv('deal_positions_clean.csv', low_memory=False)

# 类型转换
df['filing_date'] = pd.to_datetime(df['filing_date'])
df['maturity_date'] = pd.to_datetime(df['maturity_date'], errors='coerce')
df['spread_bps'] = pd.to_numeric(df['spread_bps'], errors='coerce')
df['pik_spread_bps'] = pd.to_numeric(df['pik_spread_bps'], errors='coerce')
df['fair_value_usd_mn'] = pd.to_numeric(df['fair_value_usd_mn'], errors='coerce')
df['cost_basis_usd_mn'] = pd.to_numeric(df['cost_basis_usd_mn'], errors='coerce')

# 推荐基础集
df_base = df[~df['is_anomaly']].copy()

print(f"总记录: {len(df):,}")
print(f"有效记录: {len(df_base):,}")
print(f"BDC: {df['ticker'].nunique()} 家")
print(f"时间范围: {df['filing_date'].min().date()} ~ {df['filing_date'].max().date()}")
print(f"唯一借款人(标准化): {df['borrower_name_clean'].nunique():,} 家")
```

---

## 8. 附录：BDC 完整列表

| Ticker | 记录数 | 报告期数 | 备注 |
|--------|--------|--------|------|
| ARCC | 90 | 10 | Ares Capital，最大 BDC，HTML 覆盖极不完整 |
| BCSF | 8,181 | 10 | Benefit Street Partners BDC |
| BXSL | 209 | 8 | Blackstone Secured Lending |
| CGBD | 116 | 15 | TCG BDC (Carlyle) |
| CSWC | 3,369 | 15 | Capital Southwest |
| FDUS | 597 | 15 | Fidus Investment |
| FSIC | 2,716 | 16 | FS Investment Corp |
| GBDC | 96 | 5 | Golub Capital BDC，HTML 覆盖不完整 |
| GDLC | 6 | 2 | GDL Fund，数据极少 |
| GECC | 28 | 15 | Great Elm Capital |
| HTGC | 933 | 15 | Hercules Capital（科技/生命科学 BDC）|
| ICMB | 115 | 7 | Investcorp Credit Management BDC |
| KBDC | 337 | 6 | Kayne Anderson BDC |
| LRFC | 34 | 9 | Logan Ridge Financial |
| MAIN | 4,267 | 16 | Main Street Capital |
| MFIC | 2,873 | 11 | MidCap Financial Investment |
| MRCC | 1,374 | 15 | Monroe Capital BDC |
| MSIF | 1,914 | 12 | Morgan Stanley Direct Lending |
| NCDL | 33 | 15 | Nuveen Churchill Direct Lending |
| NMFC | 319 | 15 | New Mountain Finance |
| OBDC | 2,085 | 15 | Blue Owl Capital (OBDC) |
| OBDC2 | 742 | 15 | Blue Owl Capital (OBDC2) |
| OBDE | 536 | 12 | Blue Owl Capital (OBDE) |
| OCSL | 8,943 | 15 | Oaktree Specialty Lending |
| OFS | 2,287 | 15 | OFS Capital |
| PFLT | 617 | 12 | PennantPark Floating Rate Capital |
| PNNT | 440 | 12 | PennantPark Investment |
| PSEC | 5,866 | 17 | Prospect Capital，最多报告期，小仓位为主 |
| PTMN | 2,932 | 14 | Portman Ridge Finance |
| RWAY | 130 | 14 | Runway Growth Finance |
| SAR | 71 | 12 | Saratoga Investment |
| SCM | 2,794 | 14 | Stellus Capital Investment |
| SLRC | 15 | 5 | Sierra Income (SLR)，数据极少 |
| SSSS | 39 | 10 | SuRo Capital |
| TCPC | 1,588 | 16 | BlackRock TCP Capital |
| TPVG | 3,072 | 15 | TriplePoint Venture Growth（风投 BDC）|
| TRIN | 7,189 | 15 | Trinity Capital（设备融资 BDC）|
| TSLX | 2,786 | 16 | Sixth Street Specialty Lending |
| WHF | 1,663 | 15 | WhiteHorse Finance |

---

## 引用格式

如在研究或分析中使用本数据集，请引用：

```
Fan Zeng (2026). US Private Credit: BDC Investment Data (2021-2026) [v1.3]. 
Kaggle. https://www.kaggle.com/datasets/frank970331/us-private-credit-bdc-data
```

---

**GitHub**: https://github.com/franktseng0331/us-private-credit  
**Kaggle**: https://www.kaggle.com/datasets/frank970331/us-private-credit-bdc-data  
**问题反馈**: 请在 GitHub 仓库提交 Issue
