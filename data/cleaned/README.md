# 数据清洗结果说明

## 目录结构

```
data/cleaned/
├── README.md                      # 本说明文档
├── deal_positions_clean.csv       # 清洗后的主数据文件
└── cleaning_report.json           # 清洗过程统计报告
```

---

## 文件说明

### 1. deal_positions_clean.csv

**描述**：清洗后的 BDC 私募信贷持仓数据，包含 73,960 条记录，33 个字段。

**数据来源**：`data/parsed/deal_positions.csv`（SEC EDGAR 10-Q/10-K 原始解析数据）

**清洗日期**：2026-04-16

**字段列表**：

#### 原始字段（24个，保留未修改）
| 字段名 | 说明 |
|--------|------|
| `cik` | BDC 公司 CIK 编号 |
| `bdc_name` | BDC 公司名称 |
| `filing_date` | 财报提交日期 |
| `filing_id` | SEC 财报唯一标识 |
| `report_period` | 报告期间 |
| `borrower_name` | 借款人名称（原始） |
| `industry` | 行业分类（原始，未清洗） |
| `investment_type` | 投资类型（原始，未标准化） |
| `position_size_usd_mn` | 持仓规模（百万美元） |
| `cost_basis_usd_mn` | 成本基础（百万美元） |
| `fair_value_usd_mn` | 公允价值（百万美元） |
| `base_rate` | 基准利率（原始） |
| `spread_raw` | 利差（原始字符串） |
| `is_pik` | 是否为 PIK（Payment-in-Kind） |
| `maturity_raw` | 到期日（原始字符串） |
| `is_non_accrual` | 是否为非应计资产 |
| `is_control_investment` | 是否为控制性投资 |
| `is_affiliate_investment` | 是否为关联方投资 |
| `ownership_pct` | 持股比例 |
| `notes` | 备注 |
| `table_index` | 表格索引 |
| `html_source` | HTML 来源 |
| `parsing_timestamp` | 解析时间戳 |
| `parser_version` | 解析器版本 |

#### 新增字段（9个）
| 字段名 | 说明 | 数据类型 |
|--------|------|----------|
| `investment_type_std` | 标准化投资类型（14个类别） | string |
| `industry_clean` | 清洗后的行业名称 | string |
| `industry_gics` | GICS 宏观行业分类（12个大类） | string |
| `borrower_name_clean` | 标准化借款人名称（用于跨季度追踪） | string |
| `maturity_date` | 标准化到期日（YYYY-MM-DD） | date/null |
| `spread_bps` | 利差（基点，整数） | int |
| `pik_spread_bps` | PIK 利差（基点，整数） | int |
| `is_anomaly` | 是否为数据异常（负值异常） | boolean |
| `is_unfunded_liability` | 是否为未提取负债（Revolver/Delayed Draw 负值） | boolean |

---

### 2. cleaning_report.json

**描述**：清洗过程的详细统计报告，包含每个步骤的处理结果和质量指标。

**主要内容**：

#### 元数据
- `cleaning_date`: 清洗执行时间
- `input_file`: 输入文件路径
- `output_file`: 输出文件路径
- `total_records`: 总记录数（73,960）
- `total_columns`: 总字段数（33）
- `new_columns`: 新增字段列表

#### 统计信息（statistics）

**步骤1：投资类型标准化（step1_investment_type）**
- `unknown_count`: 无法分类的记录数（4,447）
- `unknown_percentage`: Unknown 占比（6.01%，✅ 目标 <10%）
- `type_distribution`: 14个标准类别的分布

**步骤2：行业清洗与 GICS 映射（step2_industry）**
- `valid_count`: 有效行业记录数（11,176）
- `valid_percentage`: 有效率（15.11%，⚠️ 受原始数据质量限制）
- `gics_distribution`: 12个 GICS 大类的分布

**步骤3：金额单位统一（step3_unit_conversion）**
- `total_conversions`: 修正的财报数（68份）
- `conversion_log`: 每份财报的转换详情（CIK、filing_id、原始单位、中位数、转换系数、影响记录数）

**步骤4：负值异常标记（step4_negative_values）**
- `unfunded_liability_count`: 未提取负债数（0）
- `anomaly_count`: 数据异常数（1,326）
- `negative_fair_value`: 公允价值负值数（0）
- `negative_cost_basis`: 成本基础负值数（267）
- `negative_position_size`: 持仓规模负值数（1,060）

**步骤5：日期标准化（step5_date_parsing）**
- `total_debt_records`: 债务类资产总数（47,684）
- `parsed_count`: 成功解析数（42,922）
- `parse_rate_percentage`: 解析成功率（90.01%，✅ 目标 >80%）

**步骤6：利率字段提取（step6_interest_rate）**
- `base_rate_valid_count`: 基准利率提取数（41,529）
- `spread_extracted_count`: 利差提取数（17,233）
- `pik_extracted_count`: PIK 利差提取数（3,418）
- `pik_is_pik_corrected`: PIK 标记修正数（0）

**步骤7：借款人名称标准化（step7_borrower_name）**
- `unique_original`: 原始唯一借款人数（8,570）
- `unique_clean`: 清洗后唯一借款人数（7,726）
- `reduction_percentage`: 去重率（9.85%）

---

## 数据质量指标

| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| 投资类型 Unknown 占比 | 6.01% | <10% | ✅ 达标 |
| 日期解析成功率（债务类） | 90.01% | >80% | ✅ 达标 |
| 行业有效率（预回填） | 15.11% | >60% | ⚠️ 受原始数据限制 |
| GICS 有效率 | 15.00% | >55% | ⚠️ 受原始数据限制 |

**关于行业指标的说明**：
- 原始数据中约 85% 的记录缺失有效行业信息（空白、脚注、投资类型描述等）
- 清洗后的 11,176 条有效记录中，只有 172 条（0.2%）无法映射到 GICS 大类
- 在可清洗的数据范围内，GICS 覆盖率已达到最优（98.5%）
- 跨季度回填功能（通过 `borrower_name_clean`）可进一步提升有效率

---

## 清洗规则概览

### 步骤1：投资类型标准化
- 将 200+ 种原始投资类型映射到 14 个标准类别
- 优先匹配复合条件（如 "First Lien + Delayed Draw"）
- 支持股权、债务、权证、结构化产品等全类型

### 步骤2：行业清洗与 GICS 映射
- 过滤脚注、日期、投资类型描述、公司后缀等无效内容
- 映射到 12 个 GICS 宏观大类（Software & Technology、Healthcare、Industrials 等）
- 支持跨季度回填（通过标准化借款人名称）

### 步骤3：金额单位统一
- 按 BDC + filing_id 粒度判断单位（千美元/百万美元/美元）
- 统一转换为百万美元（USD millions）
- 68 份财报从千美元转换为百万美元

### 步骤4：负值异常标记
- 区分合理负值（Revolver/Delayed Draw 未提取负债）与数据异常
- 标记 1,326 条异常记录（成本基础或持仓规模为负）

### 步骤5：日期标准化
- 支持多种日期格式（Dec 2027、12/2027、12/31/2027、12/31/27）
- 自动推断两位年份（<50 → 20xx，≥50 → 19xx）
- 股权类资产允许到期日为空

### 步骤6：利率字段提取
- 标准化基准利率（SOFR、LIBOR、PRIME、Fixed）
- 提取数值型利差（基点）
- 单独提取 PIK 利差（私募信贷风险监测核心指标）

### 步骤7：借款人名称标准化
- 转大写、去除公司后缀、去除标点符号
- 用于跨季度追踪同一借款人的估值轨迹
- 去重率 9.85%（8,570 → 7,726 唯一借款人）

---

## 使用建议

### 数据分析
- 使用 `investment_type_std` 进行投资类型分析（避免使用原始 `investment_type`）
- 使用 `industry_gics` 进行行业分析（宏观层面）
- 使用 `industry_clean` 进行细分行业分析（需注意 85% 缺失率）
- 使用 `borrower_name_clean` 追踪同一借款人的跨季度表现

### 数据过滤
- 排除异常记录：`is_anomaly == False`
- 排除未提取负债：`is_unfunded_liability == False`
- 仅分析债务类资产：`investment_type_std` 不包含 Equity/Warrant

### 金额计算
- 所有金额字段已统一为百万美元（USD millions）
- 可直接进行加总、平均等计算

### 利率分析
- 总利差 = `spread_bps`（基点）
- PIK 利差 = `pik_spread_bps`（基点）
- 现金利差 = `spread_bps - pik_spread_bps`

---

## 技术细节

### 清洗脚本
- 主脚本：`src/data_cleaner.py`
- 入口脚本：`run_cleaning.py`
- 执行命令：`python3 run_cleaning.py`

### 依赖库
- pandas
- numpy
- re（正则表达式）
- json

### Git 分支
- 分支名：`feature/data-cleaning`
- 提交哈希：6132993

---

## 更新日志

### 2026-04-16
- 初始版本发布
- 完成 7 步清洗流程
- 生成清洗报告和说明文档

---

## 联系方式

如有数据质量问题或清洗规则建议，请通过 GitHub Issues 反馈。
