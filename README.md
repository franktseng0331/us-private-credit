# US Private Credit 数据采集与清洗项目

## 项目简介

本项目用于采集和清洗美国私募信贷（US Private Credit）的底层资产数据。通过 SEC EDGAR 数据库获取 BDC（业务发展公司，Business Development Company）的公开申报文件，提取 Schedule of Investments（投资明细表）中的贷款级别数据，并经过系统化的 7 步清洗流程，输出可直接用于分析的干净数据集。

**数据覆盖**：2021–2025 年（季度粒度），Top 50 BDCs，共 73,960 条持仓记录

---

## 目录

- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [数据流程概览](#数据流程概览)
- [数据字段说明](#数据字段说明)
- [数据清洗管线](#数据清洗管线)
- [数据质量指标](#数据质量指标)
- [注意事项](#注意事项)
- [下一步计划](#下一步计划)

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 User-Agent

在使用前，请修改代码中的 User-Agent（SEC 要求）：

```python
# 在 src/bdc_collector.py 中修改
user_agent = "YourCompany admin@email.com"
```

### 3. 运行爬虫（数据采集）

```python
from src.bdc_collector import BDCCollector

collector = BDCCollector(user_agent="YourCompany admin@email.com")

# 测试：下载单个BDC
collector.download_filing("0001392687", "ARCC", "10-Q")

# 批量下载所有BDC
collector.download_all_bdcs()
```

### 4. 解析数据

```python
from src.xbrl_parser import XBRLParser
from src.html_parser import HTMLParser
from pathlib import Path
import pandas as pd

xbrl_parser = XBRLParser()
html_parser = HTMLParser()

all_records = []
raw_dir = Path("data/raw/edgar")

for cik_dir in raw_dir.iterdir():
    for quarter_dir in cik_dir.iterdir():
        records = xbrl_parser.parse_filing(quarter_dir)
        if not records:
            records = html_parser.parse_filing(quarter_dir)
        all_records.extend(records)

df = pd.DataFrame(all_records)
df.to_csv("data/parsed/deal_positions.csv", index=False)
print(f"共解析 {len(df)} 条记录")
```

### 5. 运行数据清洗

```bash
python3 run_cleaning.py
```

清洗完成后输出：
- `data/cleaned/deal_positions_clean.csv` — 清洗后的主数据文件（33 个字段）
- `data/cleaned/cleaning_report.json` — 各步骤统计报告

---

## 项目结构

```
us-private-credit/
├── README.md                          # 本文档
├── 数据清洗计划.md                     # 清洗方案设计文档
├── 数据说明文档.md                     # 原始解析数据字段说明
├── run_cleaning.py                    # 数据清洗入口脚本
├── requirements.txt                   # Python 依赖
├── config/
│   └── bdc_ciks.json                  # Top 50 BDC 的 CIK 列表
├── src/
│   ├── bdc_collector.py               # SEC EDGAR 下载器
│   ├── xbrl_parser.py                 # XBRL 格式解析器（2022 年后）
│   ├── html_parser.py                 # HTML 格式解析器（2021–2022 年）
│   └── data_cleaner.py                # 数据清洗主脚本（7 步清洗流程）
├── data/
│   ├── raw/
│   │   └── edgar/{cik}/{quarter}/     # 原始 HTML/XML 文件
│   ├── parsed/
│   │   ├── deal_positions.csv         # 原始解析数据（只读，73,960 条）
│   │   ├── coverage_report.json       # 覆盖率报告
│   │   └── failed_downloads.json      # 失败下载清单
│   └── cleaned/
│       ├── README.md                  # 清洗数据详细说明
│       ├── deal_positions_clean.csv   # 清洗后主数据（33 字段）
│       └── cleaning_report.json       # 清洗过程统计报告
```

---

## 数据流程概览

```
SEC EDGAR (10-Q/10-K)
        ↓
  [数据采集] bdc_collector.py
        ↓
  data/raw/edgar/
        ↓
  [数据解析] xbrl_parser.py / html_parser.py
        ↓
  data/parsed/deal_positions.csv   ← 原始解析数据（不修改）
        ↓
  [数据清洗] data_cleaner.py（7步）
        ↓
  data/cleaned/deal_positions_clean.csv   ← 分析用干净数据
```

---

## 数据字段说明

### 原始解析字段（24 个，来自 data/parsed/deal_positions.csv）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `cik` | string | BDC 公司 CIK 编号 |
| `bdc_name` | string | BDC 公司名称 |
| `filing_date` | date | 财报提交日期 |
| `filing_id` | string | SEC 财报唯一标识 |
| `report_period` | string | 报告期间 |
| `borrower_name` | string | 借款人名称（原始） |
| `industry` | string | 行业分类（原始，未清洗） |
| `investment_type` | string | 投资类型（原始，未标准化） |
| `position_size_usd_mn` | float | 持仓规模（百万美元，清洗后统一单位） |
| `cost_basis_usd_mn` | float | 成本基础（百万美元，清洗后统一单位） |
| `fair_value_usd_mn` | float | 公允价值（百万美元，清洗后统一单位） |
| `base_rate` | string | 基准利率（清洗后标准化为 SOFR/LIBOR/PRIME/Fixed） |
| `spread_raw` | string | 利差（原始字符串） |
| `is_pik` | boolean | 是否为 PIK（Payment-in-Kind） |
| `maturity_raw` | string | 到期日（原始字符串） |
| `is_non_accrual` | boolean | 是否为非应计资产 |
| `is_control_investment` | boolean | 是否为控制性投资 |
| `is_affiliate_investment` | boolean | 是否为关联方投资 |
| `ownership_pct` | float | 持股比例 |
| `notes` | string | 备注 |
| `table_index` | int | 表格索引 |
| `html_source` | string | HTML 来源 |
| `parsing_timestamp` | string | 解析时间戳 |
| `parser_version` | string | 解析器版本 |

### 清洗新增字段（9 个，仅在 data/cleaned/deal_positions_clean.csv 中）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `investment_type_std` | string | 标准化投资类型（14 个类别） |
| `industry_clean` | string | 清洗后的行业名称 |
| `industry_gics` | string | GICS 宏观行业分类（12 个大类） |
| `borrower_name_clean` | string | 标准化借款人名称（用于跨季度追踪） |
| `maturity_date` | date | 标准化到期日（YYYY-MM-DD） |
| `spread_bps` | int | 总利差（基点） |
| `pik_spread_bps` | int | PIK 利差（基点，无 PIK 则为 0） |
| `is_anomaly` | boolean | 是否为数据异常（负值异常） |
| `is_unfunded_liability` | boolean | 是否为未提取负债（Revolver/Delayed Draw 负值） |

---

## 数据清洗管线

清洗脚本 `src/data_cleaner.py` 实现了 7 个步骤，入口脚本为 `run_cleaning.py`：

### 步骤 1：投资类型标准化
将 200+ 种原始投资类型映射到 14 个标准类别，严格按优先级顺序匹配（复合条件先于单一条件）。

| 优先级 | 标准类别 | 典型原始值示例 |
|--------|---------|--------------|
| 1 | `First Lien Delayed Draw` | "First Lien Delayed Draw Term Loan" |
| 2 | `First Lien Revolver` | "First Lien Revolving Credit Facility" |
| 3 | `First Lien Term Loan` | "Senior Secured First Lien Term Loan" |
| 4 | `Second Lien Term Loan` | "Second Lien Senior Secured Loan" |
| 5 | `Unitranche Loan` | "Unitranche Term Loan" |
| 6 | `Senior Secured Loan` | "Senior Secured Debt" |
| 7 | `Subordinated Debt` | "Mezzanine Loan", "Subordinated Note" |
| 8 | `Structured Finance / CLO` | "CLO Equity", "Structured Note" |
| 9 | `Common Equity` | "Common Stock", "LLC Interests" |
| 10 | `Preferred Equity` | "Preferred Stock", "Preferred Units" |
| 11 | `Warrant` | "Warrant to Purchase Common Stock" |
| 12 | `Unsecured Note` | "Senior Unsecured Note" |
| 13 | `Revolver` | "Revolving Credit Facility" |
| 14 | `Unknown` | 空白、特殊字符、无法匹配 |

### 步骤 2：行业清洗与 GICS 映射
过滤脚注、日期、投资类型描述、公司后缀等无效内容，将有效行业名映射到 12 个 GICS 宏观大类，并通过 `borrower_name_clean` 跨季度回填缺失值。

### 步骤 3：金额单位统一
以 BDC + filing_id（单份财报）为粒度判断单位（千美元/百万美元/美元），统一转换为百万美元（USD millions）。共修正 68 份财报。

### 步骤 4：负值异常标记
区分财务上合理的负值（Revolver/Delayed Draw 未提取负债）与数据异常，分别标记 `is_unfunded_liability` 和 `is_anomaly`。

### 步骤 5：日期标准化
支持多种格式（`Dec 2027`、`12/2027`、`12/31/2027`）解析为 `YYYY-MM-DD`，股权/权证类资产允许为空（不计入失败率）。

### 步骤 6：利率字段提取
标准化基准利率（SOFR/LIBOR/PRIME/Fixed），提取数值型利差（`spread_bps`），单独提取 PIK 利差（`pik_spread_bps`）。PIK 转换是私募信贷信用压力的早期预警信号。

### 步骤 7：借款人名称标准化
转大写 → 去除企业后缀 → 去除标点 → 去除多余空格，用于跨季度追踪同一借款人的估值轨迹。去重率 9.85%（8,570 → 7,726 唯一借款人）。

---

## 数据质量指标

| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| 投资类型 Unknown 占比 | 6.01% | <10% | ✅ 达标 |
| 日期解析成功率（债务类） | 90.01% | >80% | ✅ 达标 |
| 行业有效率（预回填） | 15.11% | >60% | ⚠️ 受原始数据限制 |
| GICS 映射覆盖率（有效行业内） | 98.5% | >95% | ✅ 达标 |

> **行业指标说明**：原始数据中约 85% 的记录缺失有效行业信息（空白、脚注、投资类型描述等），属于原始解析数据的结构性限制。在可清洗的 11,176 条有效记录中，仅 172 条（0.2%）无法映射到 GICS 大类，覆盖率已达最优。

---

## 注意事项

### SEC API 限制

- **速率限制**：10 请求/秒（已在代码中实现）
- **User-Agent 要求**：必须提供有效的 User-Agent（格式：公司名 邮箱）
- **避免重复下载**：所有原始文件会缓存到本地

### 数据使用建议

- 使用 `investment_type_std` 进行投资类型分析（不使用原始 `investment_type`）
- 使用 `industry_gics` 进行行业分析（宏观层面）
- 排除异常记录：过滤 `is_anomaly == True`
- 所有金额字段已统一为百万美元（USD millions），可直接加总计算
- 总利差 = `spread_bps`，PIK 利差 = `pik_spread_bps`，现金利差 = `spread_bps - pik_spread_bps`

### 常见问题

**Q: 下载失败怎么办？**  
A: 检查 `data/parsed/failed_downloads.json`，查看失败原因。常见原因：503（SEC 服务器繁忙，稍后重试）、404（该 BDC 该季度未提交文件）、User-Agent 格式错误。

**Q: 解析失败怎么办？**  
A: 系统会自动尝试 HTML 降级解析。若仍然失败，可能是表格格式特殊，需手动调整解析器。

**Q: 如何添加更多 BDC？**  
A: 编辑 `config/bdc_ciks.json`，添加新的 CIK 和公司信息，然后重新运行采集和清洗流程。

---

## 下一步计划

| 状态 | 任务 | 说明 |
|------|------|------|
| ✅ 已完成 | 数据采集 | SEC EDGAR 爬取 Top 50 BDC，73,960 条记录 |
| ✅ 已完成 | 数据清洗 | 7 步清洗流程，输出 `deal_positions_clean.csv` |
| 🔲 待开发 | Flow 检测 | 通过季度对比识别新增/退出交易 |
| 🔲 待开发 | 利率分析 | 计算 all-in rate，分析 SOFR + spread 分布 |
| 🔲 待开发 | 信用压力监测 | 追踪 PIK 转换率、非应计比例的季度变化 |
| 🔲 待开发 | 补充数据源 | FRED 宏观数据、8-K 重大事件申报 |
| 🔲 待开发 | 量化建模 | 预测收益率、违约概率等 |

---

## 许可证

本项目仅用于研究和教育目的。数据来源于 SEC 公开数据库。

## 联系方式

如有问题，请提交 Issue 或联系项目维护者。
