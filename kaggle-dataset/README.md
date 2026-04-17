# US Private Credit: BDC Investment Data (2021-2025)

## Overview

This dataset contains **73,960 investment-level records** from the top 50 Business Development Companies (BDCs) in the United States, covering the period from 2021 to 2025. The data has been scraped from SEC EDGAR filings and cleaned through a comprehensive 7-step pipeline.

## What are BDCs?

Business Development Companies (BDCs) are publicly traded investment firms that provide financing to small and mid-sized private companies. They are required to file quarterly reports with the SEC, including detailed schedules of their investment portfolios.

## Dataset Contents

### Main File: `deal_positions_clean.csv`
- **73,960 records** across 50 BDCs
- **33 fields** including:
  - Borrower information (name, industry)
  - Investment details (type, seniority, maturity date)
  - Financial metrics (fair value, cost basis, position size)
  - Interest rates (base rate, spread, PIK spread)
  - Metadata (filing date, period, data source)

### Mapping File: `bdc_ciks.json`
- Dictionary of 50 BDCs with their CIK numbers and company names
- Format: `{"TICKER": {"cik": "1234567", "name": "Company Name"}}`

## Data Coverage

- **Time Period**: 2021 Q1 - 2025 Q4
- **BDCs Covered**: 50 largest US BDCs by AUM
- **Investment Types**: 14 standardized categories (First Lien, Second Lien, Unsecured, Equity, etc.)
- **Industries**: 12 GICS sectors

## Data Quality

### Cleaning Pipeline (7 Steps)
1. **Investment Type Standardization**: 14 standard categories, <10% unknown
2. **Industry Mapping**: GICS sector classification
3. **Unit Normalization**: All amounts in USD millions
4. **Negative Value Flagging**: Distinguish unfunded liabilities from anomalies
5. **Date Standardization**: ISO 8601 format (YYYY-MM-DD)
6. **Interest Rate Extraction**: Base rate, spread (bps), PIK spread
7. **Borrower Name Cleaning**: Remove footnotes, standardize format

### Quality Metrics
- Investment Type Unknown Rate: 6.01%
- Maturity Date Parse Rate: 90.01% (debt instruments)
- Borrower Name Deduplication: 9.85%

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
| `maturity_date` | Investment maturity date | 2027-12-31 |
| `period_of_report` | Reporting period | 2025-09-30 |

## Use Cases

- **Private Credit Market Analysis**: Understand lending trends, pricing, and portfolio composition
- **Credit Risk Modeling**: Build models using historical performance data
- **Industry Research**: Analyze which sectors receive private credit financing
- **Interest Rate Analysis**: Study spread dynamics across different loan types
- **Portfolio Analytics**: Compare BDC investment strategies

## Data Source

All data is sourced from publicly available SEC EDGAR filings:
- **10-Q**: Quarterly reports
- **10-K**: Annual reports
- **Schedule of Investments**: Detailed portfolio holdings

Data was scraped from HTML tables and cleaned using Python (pandas, regex).

## Limitations

1. **Coverage**: Not all BDC investments are captured due to HTML parsing limitations
2. **Comparison with SEC FSDS**: This dataset has lower coverage than SEC's Financial Statement Data Sets (FSDS) which uses XBRL data
3. **Industry Classification**: 15% of records lack industry information
4. **Data Quality**: Some filings have inconsistent formatting or missing fields

## License

This dataset is released under the **MIT License**. The underlying data is public information from SEC EDGAR.

## Citation

If you use this dataset in your research or analysis, please cite:

```
Fan Zeng (2026). US Private Credit: BDC Investment Data (2021-2025). 
Retrieved from Kaggle: https://www.kaggle.com/datasets/frank970331/us-private-credit-bdc-data
```

## Updates

- **2026-04-16**: Initial release with 73,960 records
- Bug fix: Corrected unit conversion logic in step 3 (see BUGFIX.md for details)

## Contact

For questions or feedback, please open an issue on the [GitHub repository](https://github.com/franktseng0331/us-private-credit).

---

**Keywords**: private credit, BDC, business development company, leveraged loans, middle market, SEC EDGAR, investment data, credit analysis
