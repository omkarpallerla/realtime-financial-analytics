/* =====================================================================
   12_vector_similarity.sql  —  Embeddings + vector similarity
   Embeds transaction descriptions with EMBED_TEXT_768 and exposes a
   table function that returns the most similar transactions by cosine
   distance — useful for spotting look-alike fraud patterns.
   We embed all flagged txns + a 1,000-row sample to keep credits tiny.
   Run as ACCOUNTADMIN (after 11).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

CREATE OR REPLACE TABLE TXN_VECTORS AS
WITH pool AS (
  -- every flagged transaction ...
  SELECT txn_id, txn_text, amount, category, merchant, city, country, channel, is_fraud_label
  FROM FRAUD_SCORED
  UNION
  -- ... plus a random sample to compare against
  SELECT txn_id, txn_text, amount, category, merchant, city, country, channel, is_fraud_label
  FROM (SELECT * FROM TXN_FEATURES ORDER BY RANDOM() LIMIT 1000)
)
SELECT
  pool.*,
  SNOWFLAKE.CORTEX.EMBED_TEXT_768('snowflake-arctic-embed-m', txn_text) AS embedding
FROM pool;

-- Table function: 5 most similar transactions to a given txn_id.
CREATE OR REPLACE FUNCTION SIMILAR_TXNS(TARGET_ID STRING)
RETURNS TABLE (txn_id STRING, similarity FLOAT, txn_text STRING,
               amount FLOAT, category STRING, is_fraud_label BOOLEAN)
AS
$$
  SELECT
    b.txn_id,
    VECTOR_COSINE_SIMILARITY(a.embedding, b.embedding) AS similarity,
    b.txn_text, b.amount, b.category, b.is_fraud_label
  FROM TXN_VECTORS a
  JOIN TXN_VECTORS b
    ON a.txn_id = TARGET_ID AND b.txn_id <> a.txn_id
  ORDER BY similarity DESC
  LIMIT 5
$$;

-- ---- validation: pick one flagged txn and find its neighbours ----
SELECT * FROM TABLE(SIMILAR_TXNS(
  (SELECT txn_id FROM FRAUD_SCORED WHERE ai_fraud_class = 'Suspicious' LIMIT 1)
));
