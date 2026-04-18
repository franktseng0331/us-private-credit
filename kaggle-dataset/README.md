# US Private Credit: BDC Investment Data (2021-2026)

## Overview

This dataset contains **225,255 investment-level records** from 45 Business Development Companies (BDCs) in the United States, covering the period from 2021 to 2026. The data has been scraped from SEC EDGAR filings and cleaned through a comprehensive 8-step pipeline.

**v2.0 Update (2026-04-18)**: Major parser fixes tripled record coverage (+191%). ARCC records grew from ~90 to 19,657; BXSL from 331 to 10,367; NMFC from 2,044 to 9,743.

## What are BDCs?

Business Development Companies (BDCs) are publicly traded investment firms that provide financing to small and mid-sized private companies. They are required to file quarterly reports with the SEC, including detailed schedules of their investment portfolios.

## Dataset Contents

### Main File: `deal_positions_clean.csv`
- **225,255 records** across 45 BDCs
- **35 fields** including:
  - Borrower information (name, industry, GICS sector)
  - Investment details (type, seniority, maturity date)
  - Financial metrics (fair value, cost basis, position size)
  - Interest rates (base rate, spread bps, PIK spread bps)
  - Quality flags (is_anomaly, is_unfunded_liability, is_expired)
  - Metadata (filing date, period, BDC ticker)

### Mapping File: `bdc_ciks.json`
- Dictionary of BDCs with their CIK numbers and company names
- Format: `{"TICKER": {"cik": "1234567", "name": "Company Name"}}`

## Data Coverage

- **Time Period**: 2021 Q1 - 2026 Q1
- **BDCs Covered**: 45 US BDCs (ARCC, BXSL, GBDC, NMFC, MAIN, TSLX, and more)
- **Investment Types**: 14 standardized categories (First Lien, Second Lien, Unsecured, Equity, etc.)
- **Industries**: 12 GICS sectors (71.49% coverage after cross-quarter backfill)
- **Report Periods**: 727 quarterly filings

## Data Quality

### Cleaning Pipeline (8 Steps)
0. **Deduplication**: Remove exact duplicates (6,862 removed)
1. **Investment Type Standardization**: 14 standard categories, 9.73% unknown
2. **Industry Mapping**: GICS sector classification + cross-quarter backfill (71.49% valid)
3. **Unit Normalization**: All amounts in USD millions (364 filings corrected)
4. **Anomaly Flagging**: Distinguish unfunded commitments (2,486) from anomalies (4,599)
5. **Date Standardization**: ISO 8601 format, 85.84% parse rate (debt instruments)
6. **Interest Rate Extraction**: Base rate, spread (bps), PIK spread; SOFR_legacy tagging
7. **Borrower Name Cleaning**: Remove footnotes, standardize format (13.41% dedup rate)

### Quality Metrics
- Investment Type Unknown Rate: **9.73%** (target <10% ✅)
- Maturity Date Parse Rate: **85.84%** (debt instruments, target >80% ✅)
- Industry Valid Rate (after backfill): **71.49%** (target >60% ✅)
- Borrower Name Deduplication: **13.41%** (24,565 → 21,271 unique borrowers)

## Key Fields

| Field | Description | Example |
|-------|-------------|---------|
| `ticker` | BDC ticker symbol | ARCC, MAIN, TSLX |
| `borrower_name_clean` | Standardized borrower name | Acme Corporation |
| `investment_type_std` | Standardized investment type | First Lien Term Loan |
| `industry_gics` | GICS industry sector | Software & IT Services |
| `fair_value_usd_mn` | Fair value in USD millions | 25.5 |
| `cost_basis_usd_mn` | Cost basis in USD millions | 24.8 |
| `spread_bps` | Interest rate spread in basis points | 550 |
| `pik_spread_bps` | PIK spread in basis points (NaN if no PIK) | 100 |
| `maturity_date` | Investment maturity date | 2027-12-31 |
| `period_of_report` | Reporting period | 2025-09-30 |
| `is_anomaly` | Flagged as data anomaly (extreme values, etc.) | False |
| `is_unfunded_liability` | Unfunded revolver/delayed draw (FV=0) | False |
| `is_expired` | Past maturity date | False |
| `base_rate_clean` | Standardized base rate | SOFR, LIBOR, SOFR_legacy |

## Use Cases

- **Private Credit Market Analysis**: Understand lending trends, pricing, and portfolio composition
- **Credit Risk Modeling**: Build models using historical performance data
- **Industry Research**: Analyze which sectors receive private credit financing
- **Interest Rate Analysis**: Study spread dynamics across different loan types and vintages
- **PIK Monitoring**: Track payment-in-kind conversion as early credit stress signal
- **Maturity Wall Analysis**: Identify upcoming refinancing needs by vintage

## Quick Start

```python
import pandas as pd

df = pd.read_csv('deal_positions_clean.csv')
df['filing_date'] = pd.to_datetime(df['filing_date'])
df['maturity_date'] = pd.to_datetime(df['maturity_date'], errors='coerce')

# Filter clean records (exclude aggregation-row anomalies)
df_clean = df[~df['is_anomaly']]

# First lien debt only
first_lien = df_clean[df_clean['investment_type_std'] == 'First Lien Term Loan']

# PIK investments
pik_deals = df_clean[df_clean['pik_spread_bps'].notna()]

# Unfunded commitments
unfunded = df_clean[df_clean['is_unfunded_liability']]
```

## Data Source

All data is sourced from publicly available SEC EDGAR filings:
- **10-Q**: Quarterly reports
- **10-K**: Annual reports
- **Schedule of Investments**: Detailed portfolio holdings

Data was scraped from HTML tables and cleaned using Python (pandas, regex).

## Limitations

1. **Coverage**: Not all BDC investments are captured due to HTML table format variations; some BDCs (e.g., RAND) use non-standard formats not yet supported
2. **Industry Classification**: 28.51% of records lack industry information even after cross-quarter backfill
3. **Spread Data**: ~78% of records lack parsed spread_bps due to varied rate field formats
4. **Aggregation Row Contamination**: Some filings include subtotal rows (flagged as `is_anomaly`)

## License

This dataset is released under the **MIT License**. The underlying data is public information from SEC EDGAR.

## Citation

If you use this dataset in your research or analysis, please cite:

```
Fan Zeng (2026). US Private Credit: BDC Investment Data (2021-2026). 
Retrieved from Kaggle: https://www.kaggle.com/datasets/frank970331/us-private-credit-bdc-data
```

## Updates

- **2026-04-18 (v2.0)**: Major parser fixes — 3 bugs fixed in `simple_parser.py`; records 77,387 → 225,255 (+191%); BDCs 39 → 45; unique borrowers 7,726 → 21,271
- **2026-04-17 (v1.4)**: Fixed `is_unfunded_liability` detection; LLM industry classifier infrastructure
- **2026-04-17 (v1.3)**: Extreme value anomaly detection; cost_basis independent normalization; SOFR_legacy tagging
- **2026-04-16 (v1.0)**: Initial release with 73,960 records

## Contact

For questions or feedback, please open an issue on the [GitHub repository](https://github.com/franktseng0331/us-private-credit).

---

**Keywords**: private credit, BDC, business development company, leveraged loans, middle market, SEC EDGAR, investment data, credit analysis, SOFR, PIK, Schedule of Investments
