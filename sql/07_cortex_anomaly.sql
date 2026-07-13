/* =====================================================================
   07_cortex_anomaly.sql  —  Anomaly detection (SNOWFLAKE.ML)
   Flags unusual transaction-spend days and unusual market-volume days.
   NOTE: Snowflake anomaly detection requires the DETECT window to be
   AFTER the training window, so we train on the earlier history and
   detect on the most recent ~30 days.
   Run as ACCOUNTADMIN (after 06). Needs history (the synthetic data /
   generator provide ~90 days).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- Full series (used by forecasting in 08) + train/detect splits.
CREATE OR REPLACE VIEW V_SPEND_SERIES AS
  SELECT spend_date::timestamp_ntz AS ts, total_spend::float AS y FROM SPEND_DAILY;

CREATE OR REPLACE VIEW V_VOLUME_SERIES AS
  SELECT ticker AS series, trade_date::timestamp_ntz AS ts, volume::float AS y
  FROM MARKET_DAILY WHERE volume IS NOT NULL;

CREATE OR REPLACE VIEW V_SPEND_TRAIN AS
  SELECT * FROM V_SPEND_SERIES WHERE ts <  DATEADD('day', -30, CURRENT_DATE());
CREATE OR REPLACE VIEW V_SPEND_EVAL AS
  SELECT * FROM V_SPEND_SERIES WHERE ts >= DATEADD('day', -30, CURRENT_DATE());

CREATE OR REPLACE VIEW V_VOLUME_TRAIN AS
  SELECT * FROM V_VOLUME_SERIES WHERE ts <  DATEADD('day', -30, CURRENT_DATE());
CREATE OR REPLACE VIEW V_VOLUME_EVAL AS
  SELECT * FROM V_VOLUME_SERIES WHERE ts >= DATEADD('day', -30, CURRENT_DATE());

-- ---------------------------------------------------------------------
-- 1) Spend anomalies (single series)
-- ---------------------------------------------------------------------
CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION RFAP_SPEND_AD(
  INPUT_DATA       => TABLE(V_SPEND_TRAIN),
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y',
  LABEL_COLNAME     => '');

CALL RFAP_SPEND_AD!DETECT_ANOMALIES(
  INPUT_DATA       => TABLE(V_SPEND_EVAL),
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y',
  CONFIG_OBJECT     => {'prediction_interval': 0.95});

CREATE OR REPLACE TABLE SPEND_ANOMALIES AS
  SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- ---------------------------------------------------------------------
-- 2) Market-volume anomalies (one series per ticker)
-- ---------------------------------------------------------------------
CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION RFAP_VOLUME_AD(
  INPUT_DATA       => TABLE(V_VOLUME_TRAIN),
  SERIES_COLNAME    => 'SERIES',
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y',
  LABEL_COLNAME     => '');

CALL RFAP_VOLUME_AD!DETECT_ANOMALIES(
  INPUT_DATA       => TABLE(V_VOLUME_EVAL),
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
