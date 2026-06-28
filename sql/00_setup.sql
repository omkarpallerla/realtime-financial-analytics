/* =====================================================================
   00_setup.sql  —  Foundation
   Real-Time Financial Analytics Platform (RFAP)
   Creates the warehouse, database, medallion schemas, and shared stages.
   Run as ACCOUNTADMIN (trial default). Snowsight worksheet -> Run All.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------------
-- Warehouse: tiny + auto-suspend so the trial credits last.
-- ---------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS RFAP_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Real-Time Financial Analytics Platform warehouse';

USE WAREHOUSE RFAP_WH;

-- ---------------------------------------------------------------------
-- Database + medallion schemas (Bronze = raw, Silver = clean, Gold = marts)
-- ---------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS RFAP_DB
  COMMENT = 'Real-Time Financial Analytics Platform';

CREATE SCHEMA IF NOT EXISTS RFAP_DB.BRONZE COMMENT = 'Raw ingested data (market, transactions, news)';
CREATE SCHEMA IF NOT EXISTS RFAP_DB.SILVER COMMENT = 'Cleaned, typed, deduplicated';
CREATE SCHEMA IF NOT EXISTS RFAP_DB.GOLD   COMMENT = 'Business marts + AI enrichment the app reads';

USE DATABASE RFAP_DB;
USE SCHEMA BRONZE;

-- ---------------------------------------------------------------------
-- Shared JSON file format (transactions + news arrive as JSON).
-- ---------------------------------------------------------------------
CREATE FILE FORMAT IF NOT EXISTS RFAP_DB.BRONZE.JSON_FMT
  TYPE = JSON
  STRIP_OUTER_ARRAY = TRUE
  COMMENT = 'One JSON object per record; files may hold an array of records.';

-- Confirm
SHOW WAREHOUSES LIKE 'RFAP_WH';
SELECT CURRENT_DATABASE() AS db, CURRENT_SCHEMA() AS sch, CURRENT_WAREHOUSE() AS wh, CURRENT_ROLE() AS role;
