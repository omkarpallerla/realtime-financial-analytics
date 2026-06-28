"""
gold_transform.py — Snowpark SILVER -> GOLD (source of truth)
=============================================================
Same logic as the stored procedure RFAP_DB.GOLD.BUILD_GOLD in
sql/06_gold_marts.sql. Kept in version control; runnable locally:

  python snowpark/gold_transform.py
"""


def build_gold(session) -> str:
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.MARKET_DAILY AS
      WITH d AS (
        SELECT ticker, ts::date AS trade_date,
               MIN_BY(open, ts) AS open, MAX(high) AS high, MIN(low) AS low,
               MAX_BY(close, ts) AS close, SUM(volume) AS volume
        FROM RFAP_DB.SILVER.MARKET_PRICES
        GROUP BY ticker, ts::date
      )
      SELECT d.*,
             close / NULLIF(LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date), 0) - 1
               AS daily_return
      FROM d
    """).collect()

    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.SPEND_DAILY AS
      SELECT txn_ts::date AS spend_date, COUNT(*) AS txn_count,
             SUM(amount) AS total_spend, AVG(amount) AS avg_ticket
      FROM RFAP_DB.SILVER.TRANSACTIONS GROUP BY txn_ts::date
    """).collect()

    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.SPEND_BY_CATEGORY AS
      SELECT txn_ts::date AS spend_date, category, COUNT(*) AS txn_count,
             SUM(amount) AS total_spend
      FROM RFAP_DB.SILVER.TRANSACTIONS GROUP BY txn_ts::date, category
    """).collect()

    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.TXN_FEATURES AS
      SELECT t.*, HOUR(txn_ts) AS txn_hour, DAYOFWEEK(txn_ts) AS txn_dow,
             AVG(amount) OVER (PARTITION BY account_id) AS acct_avg_amount,
             amount / NULLIF(AVG(amount) OVER (PARTITION BY account_id, category), 0)
               AS amt_vs_cat_avg,
             CONCAT(merchant, ' | ', category, ' | ', city, ', ', country,
                    ' | ', channel) AS txn_text
      FROM RFAP_DB.SILVER.TRANSACTIONS t
    """).collect()

    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.NEWS AS
      SELECT * FROM RFAP_DB.SILVER.NEWS_ARTICLES
    """).collect()

    md = session.table("RFAP_DB.GOLD.MARKET_DAILY").count()
    sp = session.table("RFAP_DB.GOLD.SPEND_DAILY").count()
    return f"GOLD built: market_daily={md} spend_daily={sp}"


if __name__ == "__main__":
    import os
    from pathlib import Path
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    from snowflake.snowpark import Session
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")
    pem = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).read_bytes()
    pk = serialization.load_pem_private_key(pem, None, default_backend())
    der = pk.private_bytes(serialization.Encoding.DER,
                           serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption())
    session = Session.builder.configs({
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "private_key": der,
        "role": os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "RFAP_WH"),
        "database": "RFAP_DB", "schema": "GOLD",
    }).create()
    print(build_gold(session))
    session.close()
