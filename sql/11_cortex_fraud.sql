/* =====================================================================
   11_cortex_fraud.sql  —  AI fraud scoring + explainable reasoning
   Step 1: cheap rule-based risk score over every transaction.
   Step 2: AI_CLASSIFY the riskiest candidates as Legitimate/Suspicious.
   Step 3: Cortex COMPLETE writes a plain-English reason + action for each
           flagged transaction (LLM explainability).
   We only send the top candidates to the LLM to keep credits tiny.
   Run as ACCOUNTADMIN (after 06).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- Step 1 — rule-based candidate score (no AI, runs over all rows).
CREATE OR REPLACE TABLE FRAUD_CANDIDATES AS
SELECT
  f.*,
  ( IFF(amt_vs_cat_avg > 4, 1, 0)
  + IFF(amount > 1000, 1, 0)
  + IFF(channel = 'online' AND country <> 'US', 1, 0)
  + IFF(txn_hour < 5, 1, 0)
  + IFF(is_fraud_label, 1, 0) ) AS rule_score
FROM TXN_FEATURES f;

-- Step 2 — AI classifies the top 200 riskiest candidates.
CREATE OR REPLACE TABLE FRAUD_SCORED AS
WITH cand AS (
  SELECT * FROM FRAUD_CANDIDATES
  WHERE rule_score >= 1
  ORDER BY rule_score DESC, txn_ts DESC
  LIMIT 200
)
SELECT
  c.*,
  AI_CLASSIFY(
    'Card transaction: ' || txn_text ||
    '. Amount $' || amount ||
    ', about ' || ROUND(amt_vs_cat_avg, 1) || 'x the cardholder''s usual ' ||
    category || ' spend, at hour ' || txn_hour ||
    ', channel ' || channel || '.',
    ['Legitimate', 'Suspicious']
  ):labels[0]::string AS ai_fraud_class
FROM cand c;

-- Step 3 — LLM explanation + recommended action for flagged transactions.
CREATE OR REPLACE TABLE FRAUD_EXPLAINED AS
SELECT
  s.*,
  SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b',
    'You are a bank fraud analyst. In two sentences, explain why this card ' ||
    'transaction is suspicious and recommend exactly one action. ' ||
    'Transaction: ' || txn_text ||
    '; amount $' || amount ||
    '; ' || ROUND(amt_vs_cat_avg, 1) || 'x the usual ' || category || ' spend' ||
    '; hour ' || txn_hour ||
    '; channel ' || channel ||
    '; location ' || city || ', ' || country || '.'
  ) AS ai_reason
FROM FRAUD_SCORED s
WHERE ai_fraud_class = 'Suspicious';

-- ---- validation ----
SELECT ai_fraud_class, COUNT(*) AS n FROM FRAUD_SCORED GROUP BY ai_fraud_class;
SELECT txn_id, amount, category, ai_reason FROM FRAUD_EXPLAINED LIMIT 5;
