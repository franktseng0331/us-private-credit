# US Private Credit BDC Investment Data - 数据清洗报告

**报告日期**: 2026-04-18  
**数据版本**: v2.0  
**作者**: Fan Zeng

---

## 执行摘要

本报告总结了从 SEC EDGAR 系统收集的 45 家美国商业发展公司（BDC）投资数据的清洗过程和最终数据质量。经过 8 步清洗流程（含去重），从原始 HTML 表格数据生成了包含 **225,255 条投资记录**的高质量数据集，覆盖 2021-2026 年期间。

**关键成果**:
- ✅ 成功清洗 225,255 条投资记录（去重前 232,117，移除 6,862 条重复）
- ✅ 覆盖 45 家 BDC，727 个报告期
- ✅ **v2.0 新增**: 修复 `simple_parser.py` 三处关键 Bug，总记录数从 77,387 增至 225,255（+191%）
  - Bug 1: 单列 colspan 行跳过导致 `current_section_type` 未更新（BXSL 2025+ 格式）
  - Bug 2: `_detect_table_layout` 中 `section_kw` 缺少投资类型关键词，导致布局误判
  - Bug 3: `_find_investment_type` 缺少 `first lien`/`second lien` 关键词（NMFC 主力格式）
- ✅ **v2.0**: ARCC 记录数 ~90 → 19,657；BXSL 331 → 10,367；NMFC 2,044 → 9,743
- ✅ 行业有效率（回填后）71.49%（161,030 条），超过目标 60%
- ✅ 日期解析成功率 85.84%（债务类资产）
- ✅ 去重率 13.41%（24,565 → 21,271 唯一借款人）
- ✅ 数据质量达到生产级标准

---

## 1. 数据来源

### 1.1 数据源
- **来源**: SEC EDGAR 系统
- **文件类型**: Form 10-Q / 10-K（季度/年度报告）
- **格式**: HTML 表格（Schedule of Investments）
- **时间范围**: 2021 Q1 至 2026 Q1
- **BDC 数量**: 45 家公开交易的商业发展公司

### 1.2 数据采集与解析方法
使用 `src/bdc_collector.py` 从 SEC EDGAR 系统批量下载 HTML 格式的 10-Q/10-K 报告，再通过 `src/simple_parser.py` 提取 Schedule of Investments 投资明细数据。

`simple_parser.py` 支持三种 HTML 表格布局自动检测：
- **compact**: 每行包含公司名、投资类型和金额（单表多行格式）
- **sparse**: 公司名和数据分布在不同列中
- **multirow**: 公司名单独占一行，数据行紧随其后（NMFC、ARCC 等格式）

**局限性**:
- 部分 BDC（如 RAND）未使用标准 HTML 表格，暂无法解析
- 部分原始文件包含聚合行（如"Senior secured loans总计"）混入明细数据

---

## 2. 清洗流程

### 2.1 八步清洗管道

| 步骤 | 操作 | 目的 |
|------|------|------|
| **Step 0** | 去除重复记录 | 移除完全重复行（6,862条） |
| **Step 1** | 标准化投资类型 | 统一不同拼写和格式（14个标准类别） |
| **Step 2** | 行业字段清洗 + GICS映射 | 修正行业分类代码，映射至12个GICS大类 |
| **Step 3** | 金额单位归一化 | 将所有金额统一为百万美元（364份财报转换） |
| **Step 4** | 负值/极值异常标记 | 区分真实异常 vs 合理负值（Revolver/DD FV=0）；检测 FV > 10,000M |
| **Step 5** | 日期字段标准化 | 解析到期日（多格式支持），生成 `is_expired` 标志 |
| **Step 6** | 利率字段提取 | 提取基准利率、利差、PIK利差；标记 SOFR_legacy |
| **Step 7** | 借款人名称标准化 | 统一公司名称拼写（去重率 13.41%） |
| **Step 2b** | 跨季度行业回填 | 基于借款人名称跨期补全行业（+49,381条） |

### 2.2 关键清洗逻辑

#### Step 3: 单位归一化

**问题**: 不同 BDC 使用不同的报告单位（美元、千美元、百万美元）。

**修复逻辑**:
```python
# 若 median 在 [0.1, 500]M 合理区间，直接跳过（防止 CLO 等大仓位误触发）
if REASONABLE_LO <= fv_median <= REASONABLE_HI:
    continue

if fv_median > 500000:
    factor = 1_000_000   # 美元单位
elif fv_75th > 1000:
    factor = 1000        # 千美元单位
elif fv_median > 100:
    factor = 1000        # 千美元单位
elif fv_median < 0.001:
    factor = 1_000_000   # 极小值，美元单位
```

---

## 3. 最终数据集统计

### 3.1 基本统计

| 指标 | 数值 |
|------|------|
| **总记录数** | 225,255 |
| **BDC 数量** | 45 |
| **报告期数量** | 727 |
| **时间跨度** | 2021 Q1 至 2026 Q1 |
| **字段数量** | 35 |
| **原始解析记录** | 232,117 |
| **去重移除** | 6,862 |

### 3.2 数据完整性

| 字段 | 非空率 | 说明 |
|------|--------|------|
| `ticker` | 100% | BDC 股票代码 |
| `filing_id` | 100% | 报告唯一标识 |
| `filing_date` | 100% | 报告日期 |
| `borrower_name` | 100% | 投资公司名称 |
| `fair_value_usd_mn` | 100% | 公允价值（百万美元） |
| `investment_type_std` | 100% | 标准化投资类型 |
| `is_expired` | 100% | 是否已到期（布尔） |
| `is_anomaly` | 100% | 是否异常（含极大值/负值） |
| `is_unfunded_liability` | 100% | 是否为未放款承诺 |
| `industry_clean` | 71.49% | 行业分类（含跨季度回填） |
| `spread_bps` | ~22% | 利差（基点，NaN 表示无利差） |
| `pik_spread_bps` | ~1.5% | PIK 利差（NaN 表示无 PIK） |

### 3.3 关键数量统计

| 指标 | 数值 |
|------|------|
| **is_anomaly 总数** | 4,599 条（含极大值/负值/CB单位不一致） |
| **is_unfunded_liability 总数** | 2,486 条（Revolver/Delayed Draw FV=0） |
| **PIK 投资数量** | 3,333 条 |
| **Unknown 投资类型** | 21,907 条（9.73%） |
| **SOFR_legacy 记录** | 5,355 条（2023-07 后仍标注 LIBOR 的合同） |
| **唯一借款人（清洗后）** | 21,271 家 |

---

## 4. 数据质量评估

### 4.1 质量指标

| 维度 | 评分 | 说明 |
|------|------|------|
| **完整性** | ⭐⭐⭐⭐⭐ | 核心字段 100% 完整 |
| **准确性** | ⭐⭐⭐⭐⭐ | 单位转换算法已修复，极大值/CB异常均被标记 |
| **一致性** | ⭐⭐⭐⭐⭐ | 命名和分类已标准化；LIBOR/SOFR 基准率已清洗 |
| **时效性** | ⭐⭐⭐⭐⭐ | 覆盖至 2026 Q1 |
| **唯一性** | ⭐⭐⭐⭐⭐ | 已去重（移除 6,862 条） |

### 4.2 已知局限性

1. **数据覆盖不完整**:
   - 仅解析 HTML 格式，部分 BDC（如 RAND）使用 PDF 或非标准格式无法解析
   - 部分表格格式极为特殊，需要定制解析逻辑

2. **字段缺失**:
   - `industry_clean` 有效率 71.49%（含回填；纯原始有效率 49.57%）
   - `spread_bps` 约 22%（利率字段格式多样，提取有限）

3. **聚合行污染**:
   - 部分原始文件包含"Senior secured loans (1)"等聚合汇总行
   - 这些行产生极大异常值（>100,000M），已被 `is_anomaly` 标记

---

## 5. 使用建议

### 5.1 适用场景

✅ **推荐使用**:
- 私募信贷市场趋势分析
- BDC 投资组合研究
- 行业配置分析（industry_gics 有效率 71.49%）
- 到期分析（利用 `is_expired` 字段）
- PIK 投资筛选（利用 `pik_spread_bps.notna()` 过滤）
- Unfunded commitment 分析（利用 `is_unfunded_liability` 字段）

⚠️ **谨慎使用**:
- 单个 BDC 的完整投资组合分析（数据可能不完整）
- 金额汇总分析（建议先过滤 `is_anomaly == False`）

❌ **不推荐使用**:
- 监管合规报告（需使用官方 SEC 数据）

### 5.2 数据加载示例

```python
import pandas as pd

df = pd.read_csv('deal_positions_clean.csv')
df['filing_date'] = pd.to_datetime(df['filing_date'])
df['maturity_date'] = pd.to_datetime(df['maturity_date'], errors='coerce')

# 过滤正常记录（排除聚合行异常值）
df_clean = df[~df['is_anomaly']]

# 查看已到期投资
expired = df_clean[df_clean['is_expired']]

# 查看有 PIK 的投资
pik_deals = df_clean[df_clean['pik_spread_bps'].notna()]

# 查看未放款承诺（unfunded revolver/delayed draw）
unfunded = df_clean[df_clean['is_unfunded_liability']]

# 查看 SOFR_legacy 记录（LIBOR 退出后遗留的合同）
sofr_legacy = df_clean[df_clean['base_rate_clean'] == 'SOFR_legacy']
```

---

## 6. 更新日志

### v2.0 (2026-04-18)
- ✅ **修复 Bug 1**: `simple_parser.py` 主循环中，单列 colspan 行被 `len(cells) < 2` 直接跳过，导致 `current_section_type` 未更新 → 投资类型推断失败 → 记录丢弃（BXSL 2025+ 格式）
- ✅ **修复 Bug 2**: `_detect_table_layout()` 中 `section_kw` 缺少投资类型关键词（`first lien`、`second lien` 等），导致 BXSL 表格被误判为 `multirow` 而非 `sparse`
- ✅ **修复 Bug 3**: `_find_investment_type()` 缺少 `first lien`/`second lien`/`senior secured` 关键词，NMFC 主力投资类型"First lien (2)(12)(13)"无法识别 → 记录跳过
- ✅ **记录数大幅提升**: 77,387 → 225,255（+191%）
  - ARCC: ~90 → 19,657
  - BXSL: 331 → 10,367
  - NMFC: 2,044 → 9,743
  - GBDC: 13,733（稳定）
- ✅ **BDC 数量**: 39 → 45 家
- ✅ **报告期数量**: 494 → 727 个
- ✅ **唯一借款人**: 7,726 → 21,271 家
- ✅ 行业回填率大幅提升（49,381 条回填，有效率 71.49%）

### v1.4 (2026-04-17)
- ✅ 修复 `is_unfunded_liability` 双层 Bug（parser 过滤 FV=0 行 + cleaner 条件错误）
- ✅ LLM 行业分类基础设施（`--llm` 参数）
- ✅ LLM 分类器添加指数退避重试逻辑（max_retries=5）
- ✅ 更新 LLM 模型至 `claude-haiku-4-5`

### v1.3 (2026-04-17)
- ✅ 修复极大值异常检测（FV > 10,000M）
- ✅ 修复 cost_basis 独立归一化
- ✅ 新增 `base_rate_clean` 字段（SOFR_legacy 标注）
- ✅ 修复 Unknown 投资类型（新增衍生品/合伙权益/可转债映射）

### v1.2 (2026-04-17)
- ✅ 修复 `spread_bps` 提取失败时返回 NaN（而非 0）
- ✅ `spread_bps` 列类型升级为 `float64`

### v1.1 (2026-04-17)
- ✅ 新增去重步骤（step0）
- ✅ 重写单位转换算法
- ✅ 启用跨季度行业回填
- ✅ 新增 `is_expired` 字段

### v1.0 (2026-04-16)
- ✅ 初始发布：73,960 条记录
- ✅ 完成 7 步清洗流程
- ✅ 发布至 Kaggle: https://www.kaggle.com/datasets/frank970331/us-private-credit-bdc-data

---

## 7. 引用

如果您在研究或分析中使用此数据集，请引用：

```
Fan Zeng (2026). US Private Credit: BDC Investment Data (2021-2026). 
Retrieved from Kaggle: https://www.kaggle.com/datasets/frank970331/us-private-credit-bdc-data
```

---

## 8. 联系方式

- **GitHub**: https://github.com/franktseng0331/us-private-credit
- **Kaggle**: https://www.kaggle.com/datasets/frank970331/us-private-credit-bdc-data
- **问题反馈**: 请在 GitHub 仓库提交 Issue

---

## 附录

### A. 字段说明

完整的 35 个字段说明请参考 [README.md](README.md) 的 "数据字段说明" 部分。

---

**报告生成时间**: 2026-04-18  
**数据版本**: v2.0  
**清洗脚本**: `src/data_cleaner.py`
