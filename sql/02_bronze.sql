/* =====================================================================
   02_bronze.sql  —  Raw landing zone (BRONZE)
   Raw, append-only tables that hold data exactly as it arrives, plus the
   internal stage Snowpipe drips transaction files into.
   Run as ACCOUNTADMIN.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA BRONZE;

-- ---------------------------------------------------------------------
-- MARKET — one row per ticker per poll; full Yahoo JSON kept as VARIANT.
--   Populated by the in-cloud TASK in 04_market_ingest_task.sql.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS RAW_MARKET (
  ticker        STRING,
  payload       VARIANT,                       -- raw Yahoo chart response
  source        STRING DEFAULT 'yahoo',
  ingested_at   TIMESTAMP_NTZ DEFAULT SYSDATE()
);

-- ---------------------------------------------------------------------
-- TRANSACTIONS — loaded by Snowpipe from JSON batch files (see 03).
--   We keep the raw object as VARIANT; SILVER types/cleans it.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS RAW_TRANSACTIONS (
  record        VARIANT,
  src_file      STRING DEFAULT METADATA$FILENAME,
  ingested_at   TIMESTAMP_NTZ DEFAULT SYSDATE()
);

-- ---------------------------------------------------------------------
-- NEWS — synthetic/real financial headlines as JSON (see news_generator).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS RAW_NEWS (
  record        VARIANT,
  src_file      STRING DEFAULT METADATA$FILENAME,
  ingested_at   TIMESTAMP_NTZ DEFAULT SYSDATE()
);

-- ---------------------------------------------------------------------
-- Internal stages that the local Python loaders PUT files into.
--   TXN_STAGE  is watched by the Snowpipe PIPE.
--   NEWS_STAGE is loaded on demand (COPY in 02b block below / news lane).
-- ---------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS TXN_STAGE
  FILE_FORMAT = RFAP_DB.BRONZE.JSON_FMT
  COMMENT = 'Snowpipe watches this for transaction JSON batches';

CREATE STAGE IF NOT EXISTS NEWS_STAGE
  FILE_FORMAT = RFAP_DB.BRONZE.JSON_FMT
  COMMENT = 'Financial news JSON batches';

-- Optional: load any news files already staged (re-run any time).
COPY INTO RAW_NEWS (record)
  FROM (SELECT $1 FROM @NEWS_STAGE)
  FILE_FORMAT = (FORMAT_NAME = RFAP_DB.BRONZE.JSON_FMT)
  ON_ERROR = CONTINUE;

-- ---- validation ----
SELECT 'RAW_MARKET' AS t, COUNT(*) AS rows FROM RAW_MARKET
UNION ALL SELECT 'RAW_TRANSACTIONS', COUNT(*) FROM RAW_TRANSACTIONS
UNION ALL SELECT 'RAW_NEWS', COUNT(*) FROM RAW_NEWS;
