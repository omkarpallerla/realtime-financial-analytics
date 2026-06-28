/* =====================================================================
   16_gold_views.sql  —  App-facing views
   Clean, named views the Streamlit dashboard reads. Keeping query logic
   here (not in the app) means the app stays thin and the SQL is reusable.
   Run as ACCOUNTADMIN (after 06-13).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- ---------- MARKET ----------
-- Latest price + day change per ticker (from intraday silver).
CREATE OR REPLACE VIEW V_MARKET_LATEST AS
WITH ranked AS (
  SELECT ticker, ts, close, volume,
         ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY ts DESC) AS rn
  FROM RFAP_DB.SILVER.MARKET_PRICES
),
latest AS (SELECT * FROM ranked WHERE rn = 1),
prev   AS (
  SELECT ticker, MAX_BY(close, trade_date) AS prev_close
  FROM MARKET_DAILY
  WHERE trade_date < CURRENT_DATE()
  GROUP BY ticker
)
SELECT
  l.ticker,
  l.close                                          AS last_price,
  p.prev_close,
  l.close - p.prev_close                           AS day_change,
  DIV0(l.close - p.prev_close, p.prev_close) * 100 AS day_change_pct,
  l.volume                                         AS last_volume,
  l.ts                                             AS as_of
FROM latest l LEFT JOIN prev p ON l.ticker = p.ticker;

-- Intraday candles for the candlestick chart.
CREATE OR REPLACE VIEW V_MARKET_INTRADAY AS
  SELECT ticker, ts, open, high, low, close, volume
  FROM RFAP_DB.SILVER.MARKET_PRICES;

-- ---------- SPEND ----------
CREATE OR REPLACE VIEW V_SPEND_KPIS AS
WITH last30 AS (
  SELECT * FROM SPEND_DAILY WHERE spend_date >= DATEADD('day', -30, CURRENT_DATE())
),
prev30 AS (
  SELECT * FROM SPEND_DAILY
  WHERE spend_date >= DATEADD('day', -60, CURRENT_DATE())
    AND spend_date <  DATEADD('day', -30, CURRENT_DATE())
)
SELECT
  (SELECT SUM(total_spend) FROM last30)                          AS spend_30d,
  (SELECT SUM(txn_count)   FROM last30)                          AS txns_30d,
  (SELECT AVG(avg_ticket)  FROM last30)                          AS avg_ticket_30d,
  DIV0((SELECT SUM(total_spend) FROM last30) -
       (SELECT SUM(total_spend) FROM prev30),
       (SELECT SUM(total_spend) FROM prev30)) * 100              AS spend_mom_pct;

CREATE OR REPLACE VIEW V_SPEND_TREND AS
  SELECT spend_date, total_spend, txn_count, avg_ticket
  FROM SPEND_DAILY ORDER BY spend_date;

CREATE OR REPLACE VIEW V_CATEGORY_SHARE AS
  SELECT category, SUM(total_spend) AS total_spend, SUM(txn_count) AS txn_count
  FROM SPEND_BY_CATEGORY
  WHERE spend_date >= DATEADD('day', -30, CURRENT_DATE())
  GROUP BY category ORDER BY total_spend DESC;

-- ---------- ANOMALIES ----------
CREATE OR REPLACE VIEW V_SPEND_ANOMALIES AS
  SELECT ts::date AS day, y AS actual_spend, forecast AS expected_spend,
         lower_bound, upper_bound, is_anomaly
  FROM SPEND_ANOMALIES ORDER BY ts;

CREATE OR REPLACE VIEW V_VOLUME_ANOMALIES AS
  SELECT series AS ticker, ts::date AS day, y AS actual_volume,
         forecast AS expected_volume, is_anomaly
  FROM VOLUME_ANOMALIES WHERE is_anomaly ORDER BY ts;

-- ---------- FRAUD ----------
CREATE OR REPLACE VIEW V_FRAUD_FLAGGED AS
  SELECT txn_id, txn_ts, account_id, amount, category, merchant,
         city, country, channel, ROUND(amt_vs_cat_avg, 1) AS x_usual,
         rule_score, ai_reason
  FROM FRAUD_EXPLAINED ORDER BY txn_ts DESC;

-- ---------- FORECAST ----------
CREATE OR REPLACE VIEW V_SPEND_FORECAST AS
  SELECT forecast_date, forecast, lower_bound, upper_bound FROM SPEND_FORECAST
  ORDER BY forecast_date;

CREATE OR REPLACE VIEW V_PRICE_FORECAST AS
  SELECT ticker, forecast_date, forecast, lower_bound, upper_bound FROM PRICE_FORECAST
  ORDER BY ticker, forecast_date;

-- ---------- NEWS ----------
CREATE OR REPLACE VIEW V_NEWS_FEED AS
  SELECT published_at, ticker, headline, summary, sentiment_label, sentiment_score
  FROM NEWS_ENRICHED ORDER BY published_at DESC;

-- Daily avg news sentiment vs daily close, per ticker.
CREATE OR REPLACE VIEW V_PRICE_VS_SENTIMENT AS
WITH s AS (
  SELECT ticker, published_at::date AS d, AVG(sentiment_score) AS avg_sentiment
  FROM NEWS_ENRICHED GROUP BY ticker, published_at::date
)
SELECT m.ticker, m.trade_date, m.close, s.avg_sentiment
FROM MARKET_DAILY m
LEFT JOIN s ON s.ticker = m.ticker AND s.d = m.trade_date
ORDER BY m.ticker, m.trade_date;

-- ---- validation ----
SELECT 'market_latest' AS v, COUNT(*) AS rows FROM V_MARKET_LATEST
UNION ALL SELECT 'spend_trend', COUNT(*) FROM V_SPEND_TREND
UNION ALL SELECT 'fraud_flagged', COUNT(*) FROM V_FRAUD_FLAGGED
UNION ALL SELECT 'news_feed', COUNT(*) FROM V_NEWS_FEED;
