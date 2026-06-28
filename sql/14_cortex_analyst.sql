/* =====================================================================
   14_cortex_analyst.sql  —  Text-to-SQL with Cortex Analyst
   Cortex Analyst answers business questions in plain English by turning
   them into governed SQL from a semantic model (YAML on a stage).
   The semantic model targets base GOLD tables (built by 06/09), so this
   can run any time after those. Run as ACCOUNTADMIN.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- Stage to hold the semantic model. Server-side encryption is required.
CREATE STAGE IF NOT EXISTS RFAP_SEMANTIC_STAGE
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Holds the Cortex Analyst semantic model';

/* ---------------------------------------------------------------------
   Upload the YAML:
     Snowsight > Data > RFAP_DB > GOLD > Stages > RFAP_SEMANTIC_STAGE
       > +Files > upload models/finance_semantic_model.yaml
   Then refresh so Analyst can see it:
   --------------------------------------------------------------------- */
ALTER STAGE RFAP_SEMANTIC_STAGE REFRESH;
LS @RFAP_SEMANTIC_STAGE;   -- expect finance_semantic_model.yaml

/* The Streamlit "Ask in English" tab calls the Analyst REST endpoint
     POST /api/v2/cortex/analyst/message
   with body { "semantic_model_file":
     "@RFAP_DB.GOLD.RFAP_SEMANTIC_STAGE/finance_semantic_model.yaml", ... }
   via _snowflake.send_snow_api_request (no extra setup in SiS).

   Try in the app:
     "Which category did customers spend the most on last month?"
     "What was the average daily spend last week?"
     "Show total spend by category." */
