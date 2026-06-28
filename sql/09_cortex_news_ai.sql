/* =====================================================================
   09_cortex_news_ai.sql  —  Enrich financial news with Cortex LLM
   Adds sentiment, a bucketed label, an AI topic, and a one-line summary
   to every news article. Feeds the RAG search service (10) and the
   price-vs-sentiment chart.
   Run as ACCOUNTADMIN (after 06; needs news loaded into GOLD.NEWS).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

CREATE OR REPLACE TABLE NEWS_ENRICHED AS
WITH scored AS (
  SELECT
    n.news_id,
    n.published_at,
    n.ticker,
    n.headline,
    n.body,
    n.source,
    SNOWFLAKE.CORTEX.SENTIMENT(n.headline || '. ' || n.body)        AS sentiment_score,
    AI_CLASSIFY(n.headline || '. ' || n.body,
       ['Earnings','M&A','Regulation','Macroeconomy','Product','Analyst Rating']
    ):labels[0]::string                                             AS topic,
    SNOWFLAKE.CORTEX.SUMMARIZE(n.body)                              AS summary
  FROM NEWS n
)
SELECT
  scored.*,
  CASE WHEN sentiment_score >  0.2 THEN 'Positive'
       WHEN sentiment_score < -0.2 THEN 'Negative'
       ELSE 'Neutral' END AS sentiment_label
FROM scored;

-- ---- validation ----
SELECT sentiment_label, COUNT(*) AS n, ROUND(AVG(sentiment_score),3) AS avg_score
FROM NEWS_ENRICHED GROUP BY sentiment_label ORDER BY n DESC;
