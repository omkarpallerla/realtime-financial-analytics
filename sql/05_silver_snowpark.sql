/* =====================================================================
   05_silver_snowpark.sql  —  BRONZE -> SILVER (Snowpark Python)
   A Snowpark stored procedure cleans + types the raw data:
     - MARKET_PRICES : flattens Yahoo's nested OHLC arrays, deduped
     - TRANSACTIONS  : typed via the Snowpark DataFrame API, deduped
     - NEWS_ARTICLES : typed, deduped
   We also wire a SILVER task to run right AFTER the market task.
   Run as ACCOUNTADMIN (after 04). The Python here mirrors
   snowpark/silver_transform.py.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA SILVER;

CREATE OR REPLACE PROCEDURE SILVER.BUILD_SILVER()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  HANDLER = 'main'
AS
$$
from snowflake.snowpark.functions import col, to_timestamp_ntz
from snowflake.snowpark.types import StringType, DoubleType, BooleanType

def main(session):
    # ---- MARKET: flatten nested arrays with SQL (cleanest for VARIANT) ----
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.SILVER.MARKET_PRICES AS
      SELECT
        m.payload:chart.result[0].meta.symbol::string                          AS TICKER,
        TO_TIMESTAMP_NTZ(ts.value::number)                                     AS TS,
        GET(m.payload:chart.result[0].indicators.quote[0].open,   ts.index)::float  AS OPEN,
        GET(m.payload:chart.result[0].indicators.quote[0].high,   ts.index)::float  AS HIGH,
        GET(m.payload:chart.result[0].indicators.quote[0].low,    ts.index)::float  AS LOW,
        GET(m.payload:chart.result[0].indicators.quote[0].close,  ts.index)::float  AS CLOSE,
        GET(m.payload:chart.result[0].indicators.quote[0].volume, ts.index)::number AS VOLUME,
        m.ingested_at
      FROM RFAP_DB.BRONZE.RAW_MARKET m,
           LATERAL FLATTEN(input => m.payload:chart.result[0].timestamp) ts
      WHERE GET(m.payload:chart.result[0].indicators.quote[0].close, ts.index) IS NOT NULL
      QUALIFY ROW_NUMBER() OVER (PARTITION BY TICKER, TS ORDER BY m.ingested_at DESC) = 1
    """).collect()

    # ---- TRANSACTIONS: Snowpark DataFrame API (type + dedup) ----
    raw_txn = session.table("RFAP_DB.BRONZE.RAW_TRANSACTIONS")
    txn = raw_txn.select(
        col("record")["txn_id"].cast(StringType()).alias("TXN_ID"),
        col("record")["account_id"].cast(StringType()).alias("ACCOUNT_ID"),
        to_timestamp_ntz(col("record")["ts"].cast(StringType())).alias("TXN_TS"),
        col("record")["amount"].cast(DoubleType()).alias("AMOUNT"),
        col("record")["category"].cast(StringType()).alias("CATEGORY"),
        col("record")["merchant"].cast(StringType()).alias("MERCHANT"),
        col("record")["city"].cast(StringType()).alias("CITY"),
        col("record")["country"].cast(StringType()).alias("COUNTRY"),
        col("record")["channel"].cast(StringType()).alias("CHANNEL"),
        col("record")["is_fraud"].cast(BooleanType()).alias("IS_FRAUD_LABEL"),
    ).drop_duplicates(["TXN_ID"])
    txn.write.mode("overwrite").save_as_table("RFAP_DB.SILVER.TRANSACTIONS")

    # ---- NEWS: Snowpark DataFrame API (type + dedup) ----
    raw_news = session.table("RFAP_DB.BRONZE.RAW_NEWS")
    news = raw_news.select(
        col("record")["news_id"].cast(StringType()).alias("NEWS_ID"),
        to_timestamp_ntz(col("record")["ts"].cast(StringType())).alias("PUBLISHED_AT"),
        col("record")["ticker"].cast(StringType()).alias("TICKER"),
        col("record")["headline"].cast(StringType()).alias("HEADLINE"),
        col("record")["body"].cast(StringType()).alias("BODY"),
        col("record")["source"].cast(StringType()).alias("SOURCE"),
    ).drop_duplicates(["NEWS_ID"])
    news.write.mode("overwrite").save_as_table("RFAP_DB.SILVER.NEWS_ARTICLES")

    mp = session.table("RFAP_DB.SILVER.MARKET_PRICES").count()
    tx = txn.count()
    nw = news.count()
    return f"SILVER built: market={mp} txns={tx} news={nw}"
$$;

CALL SILVER.BUILD_SILVER();

-- ---------------------------------------------------------------------
-- Task DAG, part 1: SILVER runs AFTER the market task each cycle.
-- A child task can only be added while its parent is SUSPENDED.
-- ---------------------------------------------------------------------
ALTER TASK RFAP_DB.BRONZE.RFAP_MARKET_TASK SUSPEND;

CREATE OR REPLACE TASK RFAP_DB.SILVER.RFAP_SILVER_TASK
  WAREHOUSE = RFAP_WH
  AFTER RFAP_DB.BRONZE.RFAP_MARKET_TASK
  COMMENT = 'BRONZE -> SILVER after each market poll'
AS
  CALL RFAP_DB.SILVER.BUILD_SILVER();

-- (Resumed in 06 once the GOLD child is attached, then the root.)

-- ---- validation ----
SELECT 'MARKET_PRICES' AS t, COUNT(*) AS rows FROM SILVER.MARKET_PRICES
UNION ALL SELECT 'TRANSACTIONS', COUNT(*) FROM SILVER.TRANSACTIONS
UNION ALL SELECT 'NEWS_ARTICLES', COUNT(*) FROM SILVER.NEWS_ARTICLES;
