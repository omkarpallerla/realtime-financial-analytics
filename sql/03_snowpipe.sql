/* =====================================================================
   03_snowpipe.sql  —  Snowpipe for streaming transactions
   The local loader (ingest/snowpipe_drip.py) PUTs JSON batches to
   TXN_STAGE and calls the Snowpipe REST API; this PIPE copies each new
   file into BRONZE.RAW_TRANSACTIONS automatically.

   Snowpipe REST uses KEY-PAIR (JWT) auth. One-time setup:
   ---------------------------------------------------------------------
   1) On your machine, generate an unencrypted RSA key pair:
        openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
        openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
      (On Windows, run these in Git Bash.)
   2) Copy the PUBLIC key body (the lines BETWEEN the BEGIN/END markers,
      newlines removed) and register it on your user below.
   3) Point SNOWFLAKE_PRIVATE_KEY_PATH in config/.env at rsa_key.p8.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA BRONZE;

-- Register your public key (paste the single-line body between the markers).
-- ALTER USER <YOUR_USERNAME> SET RSA_PUBLIC_KEY='MIIBIjANBgkqh...your key...';

-- The pipe. AUTO_INGEST = FALSE because we trigger it via the REST API
-- (works with an internal stage; no cloud bucket/notifications needed).
CREATE OR REPLACE PIPE RFAP_TXN_PIPE
  AUTO_INGEST = FALSE
  COMMENT = 'Streams transaction JSON batches from TXN_STAGE into RAW_TRANSACTIONS'
AS
  COPY INTO RAW_TRANSACTIONS (record)
  FROM (SELECT $1 FROM @TXN_STAGE)
  FILE_FORMAT = (FORMAT_NAME = RFAP_DB.BRONZE.JSON_FMT);

-- Confirm the pipe exists and is ready.
SHOW PIPES LIKE 'RFAP_TXN_PIPE';
SELECT SYSTEM$PIPE_STATUS('RFAP_DB.BRONZE.RFAP_TXN_PIPE');

/* ---------------------------------------------------------------------
   Now run locally (see docs/runbook.md):
     pip install -r requirements.txt
     python ingest/transaction_generator.py     # writes JSON batches
     python ingest/snowpipe_drip.py             # PUT + notify pipe (loops)
   Then verify rows land:
     SELECT COUNT(*) FROM RAW_TRANSACTIONS;
   --------------------------------------------------------------------- */
