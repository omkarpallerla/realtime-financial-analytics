/* =====================================================================
   04_market_ingest_task.sql  —  Live market lane (runs INSIDE Snowflake)
   A Snowpark Python stored procedure calls Yahoo Finance through the
   External Access Integration and lands raw JSON into BRONZE.RAW_MARKET.
   A serverless-style TASK runs it every 5 minutes — no PC required.
   Run as ACCOUNTADMIN (after 01 + 02).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA BRONZE;

-- ---------------------------------------------------------------------
-- Stored procedure: fetch intraday candles for a list of tickers.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE INGEST_MARKET(TICKERS_CSV STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python', 'requests')
  HANDLER = 'main'
  EXTERNAL_ACCESS_INTEGRATIONS = (RFAP_YAHOO_EAI)
AS
$$
import requests
from snowflake.snowpark.functions import col, parse_json

# A browser-like User-Agent avoids Yahoo's bot throttling.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RFAP/1.0"}

def main(session, tickers_csv):
    tickers = [t.strip().upper() for t in tickers_csv.split(",") if t.strip()]
    rows = []
    for t in tickers:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
               f"?interval=5m&range=1d")
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200 and r.text:
                rows.append((t, r.text))
        except Exception as e:
            # Skip a bad ticker rather than failing the whole task run.
            continue

    if not rows:
        return "No market data fetched (check the EAI / network rule)."

    df = (session.create_dataframe(rows, schema=["ticker", "payload_str"])
                 .select(col("ticker"), parse_json(col("payload_str")).alias("payload")))
    df.write.mode("append").save_as_table("RFAP_DB.BRONZE.RAW_MARKET",
                                          column_order="name")
    return f"Ingested {len(rows)} of {len(tickers)} tickers."
$$;

-- Smoke-test the SP once (should return "Ingested N of M tickers.").
CALL INGEST_MARKET('AAPL,MSFT,NVDA,AMZN,TSLA,JPM,GS');

-- ---------------------------------------------------------------------
-- Schedule it every 5 minutes. Tasks are created suspended -> RESUME.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TASK RFAP_MARKET_TASK
  WAREHOUSE = RFAP_WH
  SCHEDULE = '5 MINUTE'
  COMMENT = 'Polls Yahoo every 5 min into BRONZE.RAW_MARKET'
AS
  CALL INGEST_MARKET('AAPL,MSFT,NVDA,AMZN,TSLA,JPM,GS');

ALTER TASK RFAP_MARKET_TASK RESUME;

-- ---- validation ----
SHOW TASKS LIKE 'RFAP_MARKET_TASK';            -- state should be 'started'
SELECT ticker, ingested_at FROM RAW_MARKET ORDER BY ingested_at DESC LIMIT 10;

/* To pause polling (e.g. overnight) and save credits:
   ALTER TASK RFAP_MARKET_TASK SUSPEND;
*/
