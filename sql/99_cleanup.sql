/* =====================================================================
   99_cleanup.sql  —  Tear everything down to free trial credits
   Run when you're done. Suspends tasks first, then drops the database,
   warehouse, and the External Access objects.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;

-- Stop the scheduled tasks before dropping (avoids dangling runs).
ALTER TASK IF EXISTS RFAP_DB.BRONZE.RFAP_MARKET_TASK SUSPEND;
ALTER TASK IF EXISTS RFAP_DB.SILVER.RFAP_SILVER_TASK SUSPEND;
ALTER TASK IF EXISTS RFAP_DB.GOLD.RFAP_GOLD_TASK     SUSPEND;

DROP DATABASE IF EXISTS RFAP_DB;
DROP WAREHOUSE IF EXISTS RFAP_WH;
DROP EXTERNAL ACCESS INTEGRATION IF EXISTS RFAP_YAHOO_EAI;
-- (network rule lived in RFAP_DB and is dropped with it)

SELECT 'RFAP fully removed.' AS status;
