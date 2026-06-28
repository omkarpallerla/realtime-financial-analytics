/* =====================================================================
   01_external_access.sql  —  Let Snowflake call the Yahoo Finance API
   This is what makes the MARKET lane run *inside* Snowflake (no PC):
   a network rule whitelists Yahoo's hosts, and an External Access
   Integration grants a stored procedure permission to reach them.
   Run as ACCOUNTADMIN.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE DATABASE RFAP_DB;
USE SCHEMA BRONZE;

-- Egress whitelist: only these hosts may be reached from our SP.
CREATE OR REPLACE NETWORK RULE RFAP_YAHOO_RULE
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('query1.finance.yahoo.com', 'query2.finance.yahoo.com')
  COMMENT = 'Yahoo Finance public chart endpoints (market data, no API key)';

-- The integration the stored procedure will reference.
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION RFAP_YAHOO_EAI
  ALLOWED_NETWORK_RULES = (RFAP_YAHOO_RULE)
  ENABLED = TRUE
  COMMENT = 'Outbound access to Yahoo Finance for the market-ingest SP';

SHOW EXTERNAL ACCESS INTEGRATIONS LIKE 'RFAP_YAHOO_EAI';
