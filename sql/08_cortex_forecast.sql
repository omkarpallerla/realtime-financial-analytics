/* =====================================================================
   08_cortex_forecast.sql  —  Forecasting (SNOWFLAKE.ML.FORECAST)
   Predicts the next 14 days of total spend and the next 7 days of each
   ticker's close price, with prediction-interval bands.
   Run as ACCOUNTADMIN (after 07; reuses the series views from 07).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- ---------------------------------------------------------------------
-- 1) Spend forecast (single series, 14 days ahead)
-- ---------------------------------------------------------------------
CREATE OR REPLACE SNOWFLAKE.ML.FORECAST RFAP_SPEND_FC(
  INPUT_DATA       => TABLE(V_SPEND_SERIES),
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y');

CALL RFAP_SPEND_FC!FORECAST(
  FORECASTING_PERIODS => 14,
  CONFIG_OBJECT       => {'prediction_interval': 0.90});

CREATE OR REPLACE TABLE SPEND_FORECAST AS
  SELECT TS AS forecast_date, FORECAST, LOWER_BOUND, UPPER_BOUND
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- ---------------------------------------------------------------------
-- 2) Price forecast (one series per ticker, 7 days ahead)
--    Price series view: close per ticker per day.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW V_PRICE_SERIES AS
  SELECT ticker AS series, trade_date::timestamp_ntz AS ts, close::float AS y
  FROM MARKET_DAILY
  WHERE close IS NOT NULL;

CREATE OR REPLACE SNOWFLAKE.ML.FORECAST RFAP_PRICE_FC(
  INPUT_DATA       => TABLE(V_PRICE_SERIES),
  SERIES_COLNAME    => 'SERIES',
  TIMESTAMP_COLNAME => 'TS',
  TARGET_COLNAME    => 'Y');

CALL RFAP_PRICE_FC!FORECAST(
  FORECASTING_PERIODS => 7,
  CONFIG_OBJECT       => {'prediction_interval': 0.90});

CREATE OR REPLACE TABLE PRICE_FORECAST AS
  SELECT SERIES AS ticker, TS AS forecast_date, FORECAST, LOWER_BOUND, UPPER_BOUND
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- ---- validation ----
SELECT 'spend_forecast' AS t, COUNT(*) AS rows FROM SPEND_FORECAST
UNION ALL SELECT 'price_forecast', COUNT(*) FROM PRICE_FORECAST;
