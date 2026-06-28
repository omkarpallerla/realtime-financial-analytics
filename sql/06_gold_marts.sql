/* =====================================================================
   06_gold_marts.sql  —  SILVER -> GOLD (business marts, Snowpark Python)
   Builds the marts the dashboard + AI read from:
     - MARKET_DAILY     : daily OHLC + daily return per ticker
     - SPEND_DAILY      : daily transaction totals
     - SPEND_BY_CATEGORY: daily spend per category
     - TXN_FEATURES     : per-transaction features for fraud/anomaly/vector
     - NEWS             : passthrough base for Cortex enrichment (09)
   Then finishes the task DAG (market -> silver -> gold) and resumes it.
   Run as ACCOUNTADMIN (after 05). Mirrors snowpark/gold_transform.py.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

CREATE OR REPLACE PROCEDURE GOLD.BUILD_GOLD()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  HANDLER = 'main'
AS
$$
def main(session):
    # ---- Daily OHLC + return per ticker ----
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.MARKET_DAILY AS
      WITH d AS (
        SELECT
          ticker,
          ts::date              AS trade_date,
          MIN_BY(open,  ts)     AS open,
          MAX(high)             AS high,
          MIN(low)              AS low,
          MAX_BY(close, ts)     AS close,
          SUM(volume)           AS volume
        FROM RFAP_DB.SILVER.MARKET_PRICES
        GROUP BY ticker, ts::date
      )
      SELECT
        d.*,
        close / NULLIF(LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date), 0) - 1
          AS daily_return
      FROM d
    """).collect()

    # ---- Daily spend totals ----
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.SPEND_DAILY AS
      SELECT
        txn_ts::date     AS spend_date,
        COUNT(*)         AS txn_count,
        SUM(amount)      AS total_spend,
        AVG(amount)      AS avg_ticket
      FROM RFAP_DB.SILVER.TRANSACTIONS
      GROUP BY txn_ts::date
    """).collect()

    # ---- Daily spend by category ----
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.SPEND_BY_CATEGORY AS
      SELECT
        txn_ts::date     AS spend_date,
        category,
        COUNT(*)         AS txn_count,
        SUM(amount)      AS total_spend
      FROM RFAP_DB.SILVER.TRANSACTIONS
      GROUP BY txn_ts::date, category
    """).collect()

    # ---- Per-transaction features (used by fraud / anomaly / vector) ----
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.TXN_FEATURES AS
      SELECT
        t.*,
        HOUR(txn_ts)      AS txn_hour,
        DAYOFWEEK(txn_ts) AS txn_dow,
        AVG(amount) OVER (PARTITION BY account_id)            AS acct_avg_amount,
        amount / NULLIF(AVG(amount)
                 OVER (PARTITION BY account_id, category), 0) AS amt_vs_cat_avg,
        CONCAT(merchant, ' | ', category, ' | ', city, ', ', country,
               ' | ', channel) AS txn_text
      FROM RFAP_DB.SILVER.TRANSACTIONS t
    """).collect()

    # ---- News passthrough (Cortex enriches in 09) ----
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.GOLD.NEWS AS
      SELECT * FROM RFAP_DB.SILVER.NEWS_ARTICLES
    """).collect()

    md = session.table("RFAP_DB.GOLD.MARKET_DAILY").count()
    sp = session.table("RFAP_DB.GOLD.SPEND_DAILY").count()
    return f"GOLD built: market_daily={md} spend_daily={sp}"
$$;

CALL GOLD.BUILD_GOLD();

-- ---------------------------------------------------------------------
-- Task DAG, part 2: GOLD runs AFTER SILVER, then resume the whole chain.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TASK RFAP_DB.GOLD.RFAP_GOLD_TASK
  WAREHOUSE = RFAP_WH
  AFTER RFAP_DB.SILVER.RFAP_SILVER_TASK
  COMMENT = 'SILVER -> GOLD after each silver build'
AS
  CALL RFAP_DB.GOLD.BUILD_GOLD();

-- Resume children first, then the root last (DAG activation order).
ALTER TASK RFAP_DB.GOLD.RFAP_GOLD_TASK     RESUME;
ALTER TASK RFAP_DB.SILVER.RFAP_SILVER_TASK RESUME;
ALTER TASK RFAP_DB.BRONZE.RFAP_MARKET_TASK RESUME;

-- ---- validation ----
SHOW TASKS IN DATABASE RFAP_DB;   -- all three should read 'started'
SELECT 'MARKET_DAILY' AS t, COUNT(*) AS rows FROM GOLD.MARKET_DAILY
UNION ALL SELECT 'SPEND_DAILY', COUNT(*) FROM GOLD.SPEND_DAILY
UNION ALL SELECT 'SPEND_BY_CATEGORY', COUNT(*) FROM GOLD.SPEND_BY_CATEGORY
UNION ALL SELECT 'TXN_FEATURES', COUNT(*) FROM GOLD.TXN_FEATURES;
