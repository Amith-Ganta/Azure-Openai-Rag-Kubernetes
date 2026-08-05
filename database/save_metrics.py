from sqlalchemy import text

from database.postgres_sql import get_resilient_engine


def save_metrics(
    company: str,
    year: int,
    metrics: dict
) -> None:
    """
    Save extracted financial metrics.

    Writes to PostgreSQL when reachable, otherwise falls back to the local
    SQLite database so ingestion never hard-fails on a Postgres outage.

    Args:
        company: Company name.
        year: Fiscal year.
        metrics: Extracted KPI dictionary.
    """
    engine = get_resilient_engine()

    query = """
    INSERT INTO financial_metrics (
        company,
        year,
        revenue,
        net_income,
        operating_income,
        cash_flow,
        total_assets,
        total_liabilities,
        risk_factors,
        growth_drivers
    )
    VALUES (
        :company,
        :year,
        :revenue,
        :net_income,
        :operating_income,
        :cash_flow,
        :total_assets,
        :total_liabilities,
        :risk_factors,
        :growth_drivers
    )
    """

    def scalar(*keys):
        """First non-null value across the given keys (alias or field name)."""
        for key in keys:
            value = metrics.get(key)
            if value is not None:
                return value
        return None

    def as_text(*keys):
        """Join a list field into text; tolerate None, str, or list."""
        value = scalar(*keys)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return "\n".join(str(item) for item in value)
        return str(value)

    # Accept both aliased (capitalized) and field-name (lower-case) keys.
    params = {
        "company": company,
        "year": str(year),
        "revenue": scalar("Revenue", "revenue"),
        "net_income": scalar("Net Income", "net_income"),
        "operating_income": scalar("Operating Income", "operating_income"),
        "cash_flow": scalar("Cash Flow from Operating Activities", "cash_flow"),
        "total_assets": scalar("Total Assets", "total_assets"),
        "total_liabilities": scalar("Total Liabilities", "total_liabilities"),
        "risk_factors": as_text("Top Risk Factors", "risk_factors"),
        "growth_drivers": as_text("Top Growth Drivers", "growth_drivers"),
    }

    with engine.begin() as connection:
        connection.execute(text(query), params)

    print(
        f"Successfully saved metrics for {company} {year}"
    )

if __name__ == "__main__":
    sample_metrics = {
        "Revenue": "$391,035",
        "Net Income": "$93,736",
        "Operating Income": "$123,216",
        "Cash Flow from Operating Activities": "$118,254",
        "Total Assets": "$364,980",
        "Total Liabilities": "$308,030",
        "Top Risk Factors": [
            'Macroeconomic conditions including inflation, interest rates, and currency fluctuations could materially impact results.',
            'High competition with aggressive pricing, short product life cycles, and rapid technological changes.',
            'Dependence on single or limited sources for certain components, with potential supply shortages.',
            'Exposure to foreign exchange rate fluctuations impacting sales and margins.',
            'Legal and regulatory challenges, including significant tax disputes such as the State Aid Decision.'
        ],
        "Top Growth Drivers": [
            'Increased Services revenue from advertising, App Store, and cloud services.',
            'Higher Mac sales driven by increased laptop demand.',
            'Continued strong iPhone sales performance.',
            'Ingest your first company financial statement (e.g., 10-K, 10-Q reports in PDF format) using the sidebar uploader.',
            'Our AI engine will parse the financial metrics, risks, and growth drivers.',
            '<button id="refreshBtn" class="refresh-button" title="Refresh data"><svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6a6 6 0 01-5.65 5.99L12 18a6 6 0 01-5.99-5.65L6 12H4a8 8 0 0016 0c0-4.42-3.58-8-8-8z"/></svg></button>t capital return program.'
        ]
    }

    save_metrics(
        company="Apple",
        year=2024,
        metrics=sample_metrics
    )