/* =====================================================================
   trial_demo/03_build_gold.sql
   Same Snowpark SILVER->GOLD logic as sql/06, WITHOUT the Task DAG.
   Builds the GOLD marts once. Run after 02_build_silver.
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
$$;

CALL GOLD.BUILD_GOLD();

SELECT 'MARKET_DAILY' AS t, COUNT(*) AS n_rows FROM GOLD.MARKET_DAILY
UNION ALL SELECT 'SPEND_DAILY', COUNT(*) FROM GOLD.SPEND_DAILY
UNION ALL SELECT 'SPEND_BY_CATEGORY', COUNT(*) FROM GOLD.SPEND_BY_CATEGORY
UNION ALL SELECT 'TXN_FEATURES', COUNT(*) FROM GOLD.TXN_FEATURES;
