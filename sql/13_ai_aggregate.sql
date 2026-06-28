/* =====================================================================
   13_ai_aggregate.sql  —  AI aggregate insights (AI_AGG)
   AI_AGG reduces many rows of text into one LLM-written summary, so the
   dashboard can show "what's the story this week" without manual SQL.
   Run as ACCOUNTADMIN (after 11 + 09).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- Spending themes over the last 7 days (one AI summary across many txns).
CREATE OR REPLACE VIEW V_AI_SPEND_INSIGHT AS
SELECT AI_AGG(
  txn_text,
  'You are a retail-banking analyst. Summarize the dominant spending themes ' ||
  'and call out any unusual or risky patterns in exactly 3 short bullet points.'
) AS insight
FROM TXN_FEATURES
WHERE txn_ts::date >= DATEADD('day', -7, CURRENT_DATE());

-- Per-ticker news narrative (AI summary of all recent headlines per stock).
CREATE OR REPLACE VIEW V_AI_NEWS_THEMES AS
SELECT
  ticker,
  COUNT(*) AS articles,
  ROUND(AVG(sentiment_score), 3) AS avg_sentiment,
  AI_AGG(
    headline,
    'Summarize the dominant narrative for this stock in 2 sentences for a trader.'
  ) AS narrative
FROM NEWS_ENRICHED
GROUP BY ticker;

-- ---- validation ----
SELECT * FROM V_AI_SPEND_INSIGHT;
SELECT * FROM V_AI_NEWS_THEMES ORDER BY articles DESC;
