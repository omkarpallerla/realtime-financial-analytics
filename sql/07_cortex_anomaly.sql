/* =====================================================================
   07_cortex_anomaly.sql  —  Anomaly detection (SNOWFLAKE.ML)
   Flags unusual transaction-spend days and unusual market-volume days
   using Snowflake's built-in unsupervised anomaly detection.
   Run as ACCOUNTADMIN (after 06). Needs history:
     - spend history comes from the transaction generator (spans ~90 days)
     - market history: run ingest/backfill_market.py once for ~3 months
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- ---------------------------------------------------------------------
-- Input series (timestamp + target). Anomaly detection is unsupervised.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW V_SPEND_SERIES AS
  SELECT spend_date::timestamp_ntz AS ts, total_spend::float AS y
  FROM SPEND_DAILY;

CREATE OR REPLACE VIEW V_VOLUME_SERIES AS
  SELECT ticker AS series, trade_date::timestamp_ntz AS ts, volume::float AS y
  FROM MARKET_DAILY
  WHERE volume IS NOT NULL;

-- ---------------------------------------------------------------------
-- 1) Spend anomalies (single series)
-- ---------------------------------------------------------------------
CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION RFAP_SPEND_AD(
  INPUT_DATA       => TABLE(V_SPEND_SERIES),
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y',
  LABEL_COLNAME     => '');

CALL RFAP_SPEND_AD!DETECT_ANOMALIES(
  INPUT_DATA       => TABLE(V_SPEND_SERIES),
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y',
  CONFIG_OBJECT     => {'prediction_interval': 0.95});

CREATE OR REPLACE TABLE SPEND_ANOMALIES AS
  SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- ---------------------------------------------------------------------
-- 2) Market-volume anomalies (one series per ticker)
-- ---------------------------------------------------------------------
CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION RFAP_VOLUME_AD(
  INPUT_DATA       => TABLE(V_VOLUME_SERIES),
  SERIES_COLNAME    => 'SERIES',
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y',
  LABEL_COLNAME     => '');

CALL RFAP_VOLUME_AD!DETECT_ANOMALIES(
  INPUT_DATA       => TABLE(V_VOLUME_SERIES),
  SERIES_COLNAME    => 'SERIES',
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y',
  CONFIG_OBJECT     => {'prediction_interval': 0.95});

CREATE OR REPLACE TABLE VOLUME_ANOMALIES AS
  SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- ---- validation: how many anomalies did we flag? ----
SELECT 'spend' AS kind, COUNT_IF(is_anomaly) AS anomalies, COUNT(*) AS points FROM SPEND_ANOMALIES
UNION ALL
SELECT 'volume', COUNT_IF(is_anomaly), COUNT(*) FROM VOLUME_ANOMALIES;
