# US Private Credit 数据采集与清洗项目

## 项目简介

本项目用于采集和清洗美国私募信贷（US Private Credit）的底层资产数据。通过 SEC EDGAR 数据库获取 BDC（业务发展公司，Business Development Company）的公开申报文件，提取 Schedule of Investments（投资明细表）中的贷款级别数据，并经过系统化的 7 步清洗流程，输出可直接用于分析的干净数据集。

**数据覆盖**：2021–2026 年（季度粒度），Top 50 BDCs，共 225,255 条持仓记录（清洗后）/ 232,117 条（原始解析）

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

```bash
# 全量重新解析（推荐）
python run_reparse.py

# 或直接调用解析器
python -c "
from src.simple_parser import SimpleParser
from pathlib import Path
import pandas as pd

parser = SimpleParser()
all_records = []
raw_dir = Path('data/raw/edgar')

for cik_dir in raw_dir.iterdir():
    for quarter_dir in cik_dir.iterdir():
        records = parser.parse_filing(quarter_dir)
        all_records.extend(records)

df = pd.DataFrame(all_records)
df.to_csv('data/parsed/deal_positions.csv', index=False)
print(f'共解析 {len(df)} 条记录')
"
```

### 5. 运行数据清洗

```bash
python run_cleaning.py
```

清洗完成后输出：
- `data/cleaned/deal_positions_clean.csv` — 清洗后的主数据文件（35 个字段）
- `data/cleaned/cleaning_report.json` — 各步骤统计报告

---

## 项目结构

```
us-private-credit/
├── README.md                          # 本文档
├── 数据清洗计划.md                     # 清洗方案设计文档
├── run_cleaning.py                    # 数据清洗入口脚本
├── run_reparse.py                     # 全量重新解析入口脚本
├── requirements.txt                   # Python 依赖
├── config/
│   └── bdc_ciks.json                  # Top 50 BDC 的 CIK 列表
├── src/
│   ├── bdc_collector.py               # SEC EDGAR 下载器
│   ├── simple_parser.py               # HTML 表格解析器（支持 compact/sparse/multirow 三种布局）
│   ├── data_cleaner.py                # 数据清洗主脚本（7 步清洗流程）
│   └── llm_industry_classifier.py     # LLM 行业分类补全（可选，需 API Key）
├── data/
│   ├── raw/
│   │   └── edgar/{cik}/{quarter}/     # 原始 HTML/XML 文件
│   ├── parsed/
│   │   ├── deal_positions.csv         # 原始解析数据（232,117 条）
│   │   ├── coverage_report.json       # 覆盖率报告
│   │   └── failed_downloads.json      # 失败下载清单
│   └── cleaned/
│       ├── deal_positions_clean.csv   # 清洗后主数据（35 字段，225,255 条）
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
  [数据解析] simple_parser.py（支持 compact/sparse/multirow 布局）
        ↓
  data/parsed/deal_positions.csv   ← 原始解析数据（232,117 条，不修改）
        ↓
  [数据清洗] data_cleaner.py（7步 + 去重）
        ↓
  data/cleaned/deal_positions_clean.csv   ← 分析用干净数据（225,255 条）
```

---

## 数据字段说明

### 原始解析字段（26 个，来自 data/parsed/deal_positions.csv）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `cik` | string | BDC 公司 CIK 编号 |
| `bdc_name` | string | BDC 公司名称 |
| `ticker` | string | BDC 股票代码 |
| `filing_date` | date | 财报提交日期 |
| `filing_id` | string | SEC 财报唯一标识 |
| `period_of_report` | string | 报告期间 |
| `borrower_name` | string | 借款人名称（原始） |
| `industry` | string | 行业分类（原始，未清洗） |
| `investment_type` | string | 投资类型（原始，未标准化） |
| `position_size_usd_mn` | float | 持仓规模（百万美元） |
| `cost_basis_usd_mn` | float | 成本基础（百万美元） |
| `fair_value_usd_mn` | float | 公允价值（百万美元） |
| `interest_rate_raw` | string | 利率（原始字符串） |
| `maturity_date_raw` | string | 到期日（原始字符串） |
| `is_non_accrual` | boolean | 是否为非应计资产 |
| `is_control_investment` | boolean | 是否为控制性投资 |
| `is_affiliate_investment` | boolean | 是否为关联方投资 |
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
| `spread_bps` | float | 总利差（基点） |
| `pik_spread_bps` | float | PIK 利差（基点，无 PIK 则为 NaN） |
| `is_anomaly` | boolean | 是否为数据异常（极大值/负值/单位不一致） |
| `is_unfunded_liability` | boolean | 是否为未提取承诺（Revolver/Delayed Draw FV=0） |

---

## 数据清洗管线

清洗脚本 `src/data_cleaner.py` 实现了 8 个步骤（含去重），入口脚本为 `run_cleaning.py`：

### 步骤 0：去除重复记录
移除完全重复行，共移除 6,862 条（232,117 → 225,255）。

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
过滤脚注、日期、投资类型描述、公司后缀等无效内容，将有效行业名映射到 12 个 GICS 宏观大类，并通过 `borrower_name_clean` 跨季度回填缺失值（回填 49,381 条，有效率从 49.6% 提升至 71.5%）。

### 步骤 3：金额单位统一
以 BDC + filing_id（单份财报）为粒度判断单位（千美元/百万美元/美元），统一转换为百万美元（USD millions）。共修正 364 份财报（含 227 份 cost_basis 独立转换）。

### 步骤 4：负值异常标记
区分财务上合理的零值/负值（Revolver/Delayed Draw 未提取承诺 FV=0）与数据异常，分别标记 `is_unfunded_liability`（2,486 条）和 `is_anomaly`（4,599 条，含极大值 FV>10,000M）。

### 步骤 5：日期标准化
支持多种格式（`Dec 2027`、`12/2027`、`12/31/2027`）解析为 `YYYY-MM-DD`，债务类资产解析成功率 85.84%，股权/权证类资产允许为空。

### 步骤 6：利率字段提取
标准化基准利率（SOFR/LIBOR/PRIME/Fixed），提取数值型利差（`spread_bps`），单独提取 PIK 利差（`pik_spread_bps`）。共 5,355 条 LIBOR 历史记录（2023-07 后）标记为 SOFR_legacy。

### 步骤 7：借款人名称标准化
转大写 → 去除企业后缀 → 去除标点 → 去除多余空格，用于跨季度追踪同一借款人的估值轨迹。去重率 13.41%（24,565 → 21,271 唯一借款人）。

---

## 数据质量指标

| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| 投资类型 Unknown 占比 | 9.73% | <10% | ✅ 达标 |
| 日期解析成功率（债务类） | 85.84% | >80% | ✅ 达标 |
| 行业有效率（回填后） | 71.49% | >60% | ✅ 达标 |
| GICS 映射覆盖率（有效行业内） | >98% | >95% | ✅ 达标 |

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
A: `simple_parser.py` 支持 compact/sparse/multirow 三种表格布局自动检测。若仍然失败，可能是表格格式特殊，需手动调试。

**Q: 如何添加更多 BDC？**  
A: 编辑 `config/bdc_ciks.json`，添加新的 CIK 和公司信息，然后重新运行采集和清洗流程。

---

## 下一步计划

| 状态 | 任务 | 说明 |
|------|------|------|
| ✅ 已完成 | 数据采集 | SEC EDGAR 爬取 Top 50 BDC |
| ✅ 已完成 | 数据解析 | `simple_parser.py` 支持 compact/sparse/multirow，225,255 条记录 |
| ✅ 已完成 | 数据清洗 | 7 步清洗流程，输出 `deal_positions_clean.csv` |
| 🔲 待开发 | N-PORT XML 解析器 | 补充 SEC N-PORT-P 月度 XML 数据，进一步提升覆盖率 |
| 🔲 待开发 | Flow 检测 | 通过季度对比识别新增/退出交易 |
| 🔲 待开发 | 利率分析 | 计算 all-in rate，分析 SOFR + spread 分布 |
| 🔲 待开发 | 信用压力监测 | 追踪 PIK 转换率、非应计比例的季度变化 |

---

## 许可证

本项目仅用于研究和教育目的。数据来源于 SEC 公开数据库。

## 联系方式

如有问题，请提交 Issue 或联系项目维护者。
