# US Private Credit BDC Investment Data - 数据清洗报告

**报告日期**: 2026-04-17  
**数据版本**: v1.4  
**作者**: Fan Zeng

---

## 执行摘要

本报告总结了从 SEC EDGAR 系统收集的 39 家美国商业发展公司（BDC）投资数据的清洗过程和最终数据质量。经过 8 步清洗流程（含去重），从原始 HTML 表格数据生成了包含 **77,387 条投资记录**的高质量数据集，覆盖 2021-2026 年期间。

**关键成果**:
- ✅ 成功清洗 77,387 条投资记录（去重前 80,023，移除 2,636 条重复）
- ✅ 覆盖 39 家 BDC，494 个报告期
- ✅ 修复单位转换算法，防止合法大仓位触发过度转换
- ✅ 新增 `is_expired` 字段（16,157 条已到期）
- ✅ 修复 PIK 利差缺失值（NaN 替代 0）
- ✅ 启用跨季度行业回填（新增 1,516 条有效行业标签）
- ✅ **v1.3 新增**: 极大值异常检测（FV/CB > 10,000M），`is_anomaly` 总数升至 4,577
- ✅ **v1.3 新增**: cost_basis 独立归一化（242 filing 级 + 204 行级）
- ✅ **v1.3 新增**: PIK 正则扩展，有效记录 3,379→3,529
- ✅ **v1.3 新增**: `base_rate_clean` 字段（955 条 SOFR_legacy），总字段数升至 35
- ✅ **v1.3 新增**: Unknown 投资类型降至 3,828（-506 条）
- ✅ **v1.4 新增**: 修复 `is_unfunded_liability` 双层 Bug，**424 条** unfunded commitments 正确标记（+5,700 条新记录）
- ✅ **v1.4 新增**: LLM 行业分类补全基础设施（`--llm` 模式），待 API 恢复后可提升 `industry_clean` 至 70%+
- ✅ 数据质量达到生产级标准

---

## 1. 数据来源

### 1.1 数据源
- **来源**: SEC EDGAR 系统
- **文件类型**: Form N-PORT（季度投资组合报告）
- **格式**: HTML 表格
- **时间范围**: 2021-01-06 至 2026-02-27
- **BDC 数量**: 39 家公开交易的商业发展公司

### 1.2 数据采集方法
使用 Python 脚本从 SEC EDGAR 系统下载并解析 HTML 格式的 N-PORT 表格，提取投资持仓明细数据。

**局限性**: 
- 仅解析 HTML 格式表格，未包含 XBRL 格式数据
- 部分 BDC 的数据覆盖不完整
- 部分原始文件包含聚合行（如"Senior secured loans总计"）混入明细数据

---

## 2. 清洗流程

### 2.1 八步清洗管道

| 步骤 | 操作 | 目的 |
|------|------|------|
| **Step 0** | 去除重复记录 | 移除完全重复行（2,636条） |
| **Step 1** | 标准化投资类型 | 统一不同拼写和格式 |
| **Step 2** | 行业字段清洗 + GICS映射 | 修正行业分类代码 |
| **Step 3** | 金额单位归一化 | 将所有金额统一为百万美元 |
| **Step 4** | 负值/极值异常标记 | 区分真实异常 vs 合理负值（Revolver）；检测 FV/CB > 10,000M |
| **Step 5** | 日期字段标准化 + is_expired | 解析到期日并生成到期标志 |
| **Step 6** | 利率字段提取 | 提取基准利率、利差、PIK利差；生成 base_rate_clean |
| **Step 7** | 借款人名称标准化 | 统一公司名称拼写 |
| **Step 2b** | 跨季度行业回填 | 基于借款人名称跨期补全行业 |
| **Step LLM** | LLM 行业分类补全 | 用 `--llm` 参数启用，覆盖无行业标签的记录 |

### 2.2 关键清洗逻辑

#### Step 3: 单位归一化（v1.1 重写）

**问题**: 不同 BDC 使用不同的报告单位（美元、千美元、百万美元）。

**v1.1 修复逻辑**:
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

详见 [BUGFIX.md](BUGFIX.md)

---

## 3. 最终数据集统计

### 3.1 基本统计

| 指标 | 数值 |
|------|------|
| **总记录数** | 77,387 |
| **BDC 数量** | 39 |
| **报告期数量** | 494 |
| **时间跨度** | 2021-01-06 至 2026-02-27 |
| **字段数量** | 35 |

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
| `is_unfunded_liability` | 100% | 是否为未放款承诺（Revolver/Delayed Draw） |
| `base_rate_clean` | 100% | 清洗后基准利率（含 SOFR_legacy 标注） |
| `industry_clean` | 17.5% | 行业分类（受限于原始数据；`--llm` 模式可提升至 70%+） |
| `spread_bps` | 23.4% | 利差（基点，NaN 表示无利差或提取失败） |
| `pik_spread_bps` | 4.9% | PIK 利差（NaN 表示无 PIK） |

### 3.3 金额统计（排除聚合行异常值）

| 指标 | 数值（百万美元） |
|------|------------------|
| **中位数单笔投资** | $3.04M |
| **is_anomaly 总数** | 4,577 条（含极大值/负值/CB单位不一致） |
| **is_unfunded_liability 总数** | 424 条（Delayed Draw 333, Revolver 62, First Lien Revolver 29） |
| **已到期投资数量** | 16,157 条 |
| **PIK 投资数量** | 3,529 条 |
| **Unknown 投资类型** | 3,828 条（5.3%） |
| **SOFR_legacy 记录** | 955 条（2023-07 后仍标注 LIBOR 的合同） |

---

## 4. 数据质量评估

### 4.1 质量指标

| 维度 | 评分 | 说明 |
|------|------|------|
| **完整性** | ⭐⭐⭐⭐⭐ | 核心字段 100% 完整 |
| **准确性** | ⭐⭐⭐⭐⭐ | 单位转换算法已修复，极大值/CB异常均被标记 |
| **一致性** | ⭐⭐⭐⭐⭐ | 命名和分类已标准化；LIBOR/SOFR 基准率已清洗 |
| **时效性** | ⭐⭐⭐⭐⭐ | 覆盖至 2026-02 |
| **唯一性** | ⭐⭐⭐⭐⭐ | 已去重（移除2,636条） |

### 4.2 已知局限性

1. **数据覆盖不完整**: 
   - 仅解析 HTML 格式，未包含 XBRL 数据
   - 部分 BDC 的记录数量较少

2. **字段缺失**:
   - `industry_clean` 有效率仅 17.5%（原始 N-PORT 表格 industry 字段普遍缺失；可用 `--llm` 参数提升至 70%+）
   - `spread_bps` 仅 23.4%（利率字段格式多样，提取有限）

3. **聚合行污染**:
   - 部分原始文件包含"Senior secured loans (1)"等聚合汇总行
   - 这些行产生极大异常值（>100,000M），已被 `is_anomaly` 标记

4. **时间覆盖**:
   - 2026 年数据仅覆盖至 2 月

---

## 5. 使用建议

### 5.1 适用场景

✅ **推荐使用**:
- 私募信贷市场趋势分析
- BDC 投资组合研究
- 行业配置分析
- 到期分析（利用 `is_expired` 字段）
- PIK 投资筛选（利用 `pik_spread_bps.notna()` 过滤）
- Unfunded commitment 分析（利用 `is_unfunded_liability` 字段）

⚠️ **谨慎使用**:
- 单个 BDC 的完整投资组合分析（数据可能不完整）
- 金额汇总分析（建议先过滤 `is_anomaly == False`）
- 行业分析（`industry_clean` 有效率仅 17.5%，除非使用 `--llm` 运行）

❌ **不推荐使用**:
- 监管合规报告（需使用官方 SEC 数据）
- 需要 XBRL 格式特有字段的分析

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

### v1.4 (2026-04-17)
- ✅ 修复 `is_unfunded_liability` 双层 Bug（parser 过滤 FV=0 行 + cleaner 条件错误）：424 条 unfunded commitments 正确标记；总记录数 71,687→77,387（+5,700 条新记录）
- ✅ 修复 LLM 行业分类 `no_ind_mask` 空字符串 Bug：正确识别 64,699 条待分类记录（之前错误识别 0 条）
- ✅ 更新 LLM 模型至 `claude-haiku-4-5`（`claude-3-5-haiku-20241022` EOL 2026-02-19）
- ✅ LLM 分类器添加指数退避重试逻辑（max_retries=5，1/2/4/8/16s）
- ✅ `is_anomaly` 总数升至 4,577（新增 FV=0 unfunded 行的极值检测）

### v1.3 (2026-04-17)
- ✅ 修复 `step4` 极大值异常检测（Rule 4）：FV > 10,000M 一律标记为 `is_anomaly`，总数 1,232→3,457
- ✅ 修复 `step4` cost_basis 单位不一致检测（Rule 4b）：cb/fv 比值 > 100 且 cb > 10,000M 标记为异常（+204 条）
- ✅ 修复 `step3` cost_basis 独立归一化：fair_value 已合理时独立检测并转换 cost_basis（+242 filing 级转换）
- ✅ 修复 `step6` PIK 正则：新增格式2分支匹配 "PIK Fixed Interest Rate X.X%"，有效记录 3,379→3,529
- ✅ 新增 `base_rate_clean` 字段：955 条 2023-07 后 LIBOR 记录重标为 `SOFR_legacy`；总字段数 34→35
- ✅ 修复 `step1` Unknown 投资类型：新增衍生品/合伙权益/可转债映射，Unknown 4,334→3,828（-506）

### v1.2 (2026-04-17)
- ✅ 修复 `spread_bps` 利差：提取失败时返回 NaN（而非 0），与 `pik_spread_bps` 语义一致
- ✅ `spread_bps` 列类型从 `int64` 升级为 `float64`，虚假零值从 54,911 条降至 19 条（真实零利差）
- ✅ 有效利差记录（>0）保持 16,776 条不变

### v1.1 (2026-04-17)
- ✅ 新增去重步骤（step0），移除 2,273 条重复记录
- ✅ 重写单位转换算法，修复过度转换 bug（单次判断+合理区间保护）
- ✅ 启用跨季度行业回填（step2_backfill_industry），回填 1,516 条
- ✅ 新增 `is_expired` 字段（15,421 条到期投资）
- ✅ 修复 PIK 利差：缺失值改为 NaN（而非 0）
- ✅ 总字段数从 33 增至 34

### v1.0 (2026-04-16)
- ✅ 初始发布：73,960 条记录（含重复）
- ✅ 修复单位转换阈值 bug（转换数量从 68 增至 309）
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

完整的 35 个字段说明请参考 [README.md](README.md) 的 "Dataset Contents" 部分。

### B. Bug 修复详情

v1.0～v1.4 所有 bug 修复详情请参考 [BUGFIX.md](BUGFIX.md)。

---

**报告生成时间**: 2026-04-17  
**数据版本**: v1.4  
**清洗脚本**: `src/data_cleaner.py`
