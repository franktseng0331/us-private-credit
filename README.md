# US Private Credit 数据爬取项目

## 项目简介

本项目用于爬取美国私募信贷（US Private Credit）的底层资产数据，通过SEC EDGAR数据库获取BDC（业务发展公司）的公开申报文件，提取Schedule of Investments（投资明细表）中的贷款级别数据。

**数据覆盖**：2021-2025年（季度粒度），Top 50 BDCs，预计约54,000条交易记录

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置User-Agent

在使用前，请修改代码中的User-Agent（SEC要求）：

```python
# 在 src/bdc_collector.py 中修改
user_agent = "YourCompany admin@email.com"
```

### 3. 运行爬虫

```python
from src.bdc_collector import BDCCollector

# 初始化采集器
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

# 初始化解析器
xbrl_parser = XBRLParser()
html_parser = HTMLParser()

# 解析所有下载的文件
all_records = []
raw_dir = Path("data/raw/edgar")

for cik_dir in raw_dir.iterdir():
    for quarter_dir in cik_dir.iterdir():
        # 尝试XBRL解析
        records = xbrl_parser.parse_filing(quarter_dir)
        
        # 如果失败，尝试HTML解析
        if not records:
            records = html_parser.parse_filing(quarter_dir)
        
        all_records.extend(records)

# 保存到CSV
df = pd.DataFrame(all_records)
df.to_csv("data/parsed/deal_positions.csv", index=False)
print(f"共解析 {len(df)} 条记录")
```

### 5. 验证数据质量

```python
from src.data_validator import DataValidator

# 初始化验证器
validator = DataValidator()

# 执行验证
report = validator.validate_data()

# 查看报告
print(f"总记录数: {report['total_records']}")
print(f"数据完整性: {report['completeness']}")
print(f"覆盖率: {report['coverage']}")
```

## 项目结构

```
us-private-credit/
├── config/
│   └── bdc_ciks.json              # Top 50 BDC的CIK列表
├── src/
│   ├── bdc_collector.py           # SEC EDGAR下载器
│   ├── xbrl_parser.py             # XBRL格式解析器（2022年后）
│   ├── html_parser.py             # HTML格式解析器（2021-2022年）
│   └── data_validator.py          # 数据质量检查
├── data/
│   ├── raw/
│   │   └── edgar/{cik}/{quarter}/ # 原始HTML/XML文件
│   └── parsed/
│       ├── deal_positions.csv     # 主数据表
│       ├── coverage_report.json   # 覆盖率报告
│       ├── quality_report.json    # 数据质量报告
│       └── failed_downloads.json  # 失败下载清单
├── requirements.txt
└── README.md
```

## 数据字段说明

### deal_positions.csv 主要字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| cik | string | SEC分配的唯一公司标识 |
| bdc_name | string | BDC公司名称 |
| ticker | string | 股票代码 |
| filing_date | date | 文件提交日期 |
| quarter | string | 季度标签（如"2024-Q3"） |
| borrower_name | string | 借款企业名称 |
| industry | string | 所属行业 |
| investment_type | string | 投资类型 |
| seniority | string | 优先级（First Lien/Second Lien等） |
| interest_rate_raw | string | 原始利率文本 |
| maturity_raw | string | 原始到期日文本 |
| position_size_usd_mn | float | 持仓本金金额（百万美元） |
| cost_basis_usd_mn | float | 持仓成本（百万美元） |
| fair_value_usd_mn | float | 公允价值（百万美元） |
| data_source | string | 数据来源（XBRL/HTML） |

完整字段列表请参考项目计划文档。

## 注意事项

### SEC API限制

- **速率限制**：10请求/秒（已在代码中实现）
- **User-Agent要求**：必须提供有效的User-Agent（格式：公司名 邮箱）
- **避免重复下载**：所有原始文件会缓存到本地

### 数据质量

- **解析准确率**：目标>90%
- **覆盖率**：Top 10 BDCs应达到16/16季度
- **必填字段缺失率**：应<5%

### 常见问题

**Q: 下载失败怎么办？**
A: 检查`data/parsed/failed_downloads.json`，查看失败原因。常见原因：
- 503错误：SEC服务器繁忙，稍后重试
- 404错误：该BDC在该季度未提交文件
- User-Agent错误：检查User-Agent格式

**Q: 解析失败怎么办？**
A: 系统会自动尝试HTML降级解析。如果仍然失败，可能是表格格式特殊，需要手动调整解析器。

**Q: 如何添加更多BDC？**
A: 编辑`config/bdc_ciks.json`，添加新的CIK和公司信息。

## 下一步计划

当前项目仅完成数据采集层。后续可以：

1. **数据清洗**：借款人名称标准化、利率格式解析
2. **Flow检测**：通过季度对比识别新增/退出交易
3. **利率标准化**：计算all_in_rate（基准利率+利差）
4. **补充数据源**：FRED宏观数据、8-K重大事件申报
5. **量化建模**：预测收益率、违约概率等

## 许可证

本项目仅用于研究和教育目的。数据来源于SEC公开数据库。

## 联系方式

如有问题，请提交Issue或联系项目维护者Frank:
oleapfrank@gmail.com
