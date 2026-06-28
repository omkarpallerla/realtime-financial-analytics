/* =====================================================================
   10_cortex_search.sql  —  RAG index over financial news (Cortex Search)
   Builds a managed vector search service the dashboard's copilot/agent
   uses to retrieve relevant news for a question (grounded answers).
   Run as ACCOUNTADMIN (after 09).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

CREATE OR REPLACE CORTEX SEARCH SERVICE RFAP_NEWS_SEARCH
  ON body
  ATTRIBUTES ticker, headline, sentiment_label, sentiment_score, published_at
  WAREHOUSE = RFAP_WH
  TARGET_LAG = '1 hour'
  COMMENT = 'RAG search over enriched financial news'
AS (
  SELECT
    news_id,
    body,
    headline,
    ticker,
    sentiment_label,
    sentiment_score,
    published_at
  FROM NEWS_ENRICHED
);

-- Confirm + quick relevance test.
SHOW CORTEX SEARCH SERVICES LIKE 'RFAP_NEWS_SEARCH';

SELECT PARSE_JSON(
  SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
    'RFAP_DB.GOLD.RFAP_NEWS_SEARCH',
    '{"query": "Why did tech stocks move?", "columns": ["headline","ticker","sentiment_label"], "limit": 5}'
  )
):results AS sample_hits;
