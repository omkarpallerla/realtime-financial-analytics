/* =====================================================================
   trial_demo/01_load_synthetic.sql
   Trial accounts block External Access (so the live Yahoo Task can't run)
   and Snowpipe needs local key-pair auth. This script loads realistic
   SYNTHETIC market, transaction, and news data straight into BRONZE so
   the whole platform + dashboard works 100% in-database, no local steps.
   The production Snowpipe/Task lanes remain in sql/03,04 + ingest/.
   Run as ACCOUNTADMIN after sql/00 + sql/02.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA BRONZE;

/* ---------------------------------------------------------------------
   1) MARKET — 90 daily candles per ticker, stored in the SAME nested
      Yahoo-chart JSON shape the SILVER parser expects. Prices follow a
      geometric random walk (cumulative daily returns).
   --------------------------------------------------------------------- */
TRUNCATE TABLE IF EXISTS RAW_MARKET;

INSERT INTO RAW_MARKET (ticker, payload, source)
WITH tickers AS (
  SELECT column1 AS ticker, column2 AS base FROM VALUES
    ('AAPL',230),('MSFT',450),('NVDA',120),('AMZN',185),
    ('TSLA',250),('JPM',200),('GS',480)
),
days AS (SELECT SEQ4() AS d FROM TABLE(GENERATOR(ROWCOUNT => 90))),
grid AS (
  SELECT t.ticker, t.base, d.d,
         DATEADD('day', -(89 - d.d), CURRENT_DATE()) AS trade_date,
         NORMAL(0.0004, 0.02, RANDOM()) AS ret
  FROM tickers t CROSS JOIN days d
),
walk AS (
  SELECT ticker, base, d, trade_date,
         base * EXP(SUM(ret) OVER (PARTITION BY ticker ORDER BY d
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)) AS close
  FROM grid
),
bars AS (
  SELECT ticker, trade_date,
         DATE_PART('epoch_second', trade_date::timestamp_ntz)::number AS ts_epoch,
         ROUND(close, 2) AS close,
         ROUND(close * (1 + NORMAL(0, 0.004, RANDOM())), 2) AS open,
         (1000000 + UNIFORM(0, 9000000, RANDOM()))::number AS volume
  FROM walk
),
bars2 AS (
  SELECT ticker, ts_epoch, open, close, volume,
         ROUND(GREATEST(open, close) * (1 + ABS(NORMAL(0, 0.006, RANDOM()))), 2) AS high,
         ROUND(LEAST(open, close)  * (1 - ABS(NORMAL(0, 0.006, RANDOM()))), 2) AS low
  FROM bars
)
SELECT ticker,
  OBJECT_CONSTRUCT(
    'chart', OBJECT_CONSTRUCT(
      'result', ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
          'meta', OBJECT_CONSTRUCT('symbol', ticker),
          'timestamp', ARRAY_AGG(ts_epoch) WITHIN GROUP (ORDER BY ts_epoch),
          'indicators', OBJECT_CONSTRUCT(
            'quote', ARRAY_CONSTRUCT(
              OBJECT_CONSTRUCT(
                'open',   ARRAY_AGG(open)   WITHIN GROUP (ORDER BY ts_epoch),
                'high',   ARRAY_AGG(high)   WITHIN GROUP (ORDER BY ts_epoch),
                'low',    ARRAY_AGG(low)    WITHIN GROUP (ORDER BY ts_epoch),
                'close',  ARRAY_AGG(close)  WITHIN GROUP (ORDER BY ts_epoch),
                'volume', ARRAY_AGG(volume) WITHIN GROUP (ORDER BY ts_epoch)
              )
            )
          )
        )
      )
    )
  ) AS payload,
  'synthetic'
FROM bars2
GROUP BY ticker;

/* ---------------------------------------------------------------------
   2) TRANSACTIONS — 40k card transactions over 90 days, ~2% fraud with
      anomalous patterns (foreign, online, odd hours, big amounts).
   --------------------------------------------------------------------- */
TRUNCATE TABLE IF EXISTS RAW_TRANSACTIONS;

INSERT INTO RAW_TRANSACTIONS (record)
WITH g AS (
  SELECT
    UUID_STRING() AS txn_id,
    'ACCT' || (1000 + UNIFORM(0, 199, RANDOM()))::int AS account_id,
    DATEADD('minute', -UNIFORM(0, 129600, RANDOM()), CURRENT_TIMESTAMP())::timestamp_ntz AS ts0,
    UNIFORM(0::float, 1::float, RANDOM()) AS fraud_r,
    UNIFORM(1, 9, RANDOM()) AS cat_i,
    UNIFORM(0::float, 1::float, RANDOM()) AS chan_r,
    UNIFORM(1, 5, RANDOM()) AS fc_i,
    UNIFORM(1, 500, RANDOM()) AS merch_i,
    UNIFORM(1, 80, RANDOM()) AS city_i
  FROM TABLE(GENERATOR(ROWCOUNT => 40000))
),
e AS (
  SELECT g.*,
    (fraud_r < 0.02) AS is_fraud,
    CASE cat_i WHEN 1 THEN 'Groceries' WHEN 2 THEN 'Dining' WHEN 3 THEN 'Shopping'
               WHEN 4 THEN 'Transport' WHEN 5 THEN 'Utilities' WHEN 6 THEN 'Entertainment'
               WHEN 7 THEN 'Travel' WHEN 8 THEN 'Health' ELSE 'Electronics' END AS category0
  FROM g
),
f AS (
  SELECT
    txn_id, account_id, is_fraud, merch_i, city_i,
    CASE WHEN is_fraud THEN (CASE WHEN fc_i <= 1 THEN 'Electronics'
                                  WHEN fc_i = 2 THEN 'Shopping' ELSE 'Travel' END)
         ELSE category0 END AS category,
    CASE WHEN is_fraud THEN ROUND(UNIFORM(800, 5000, RANDOM()), 2)
         ELSE ROUND(
           CASE category0
             WHEN 'Groceries'     THEN UNIFORM(8, 180, RANDOM())
             WHEN 'Dining'        THEN UNIFORM(10, 120, RANDOM())
             WHEN 'Shopping'      THEN UNIFORM(15, 400, RANDOM())
             WHEN 'Transport'     THEN UNIFORM(3, 60, RANDOM())
             WHEN 'Utilities'     THEN UNIFORM(40, 300, RANDOM())
             WHEN 'Entertainment' THEN UNIFORM(10, 90, RANDOM())
             WHEN 'Travel'        THEN UNIFORM(80, 1500, RANDOM())
             WHEN 'Health'        THEN UNIFORM(15, 500, RANDOM())
             ELSE UNIFORM(50, 2500, RANDOM()) END, 2) END AS amount,
    CASE WHEN is_fraud OR chan_r < 0.35 THEN 'online' ELSE 'in_store' END AS channel,
    CASE WHEN is_fraud THEN (CASE fc_i WHEN 1 THEN 'NG' WHEN 2 THEN 'RU'
                                       WHEN 3 THEN 'CN' WHEN 4 THEN 'BR' ELSE 'RO' END)
         ELSE 'US' END AS country,
    CASE WHEN is_fraud THEN DATEADD('hour', (UNIFORM(1, 4, RANDOM()) - HOUR(ts0)), ts0)
         ELSE ts0 END AS ts
  FROM e
)
SELECT OBJECT_CONSTRUCT(
  'txn_id', txn_id,
  'account_id', account_id,
  'ts', TO_CHAR(ts, 'YYYY-MM-DD"T"HH24:MI:SS'),
  'amount', amount,
  'category', category,
  'merchant', 'Merchant ' || merch_i::int,
  'city', 'City ' || city_i::int,
  'country', country,
  'channel', channel,
  'is_fraud', is_fraud
)
FROM f;

/* ---------------------------------------------------------------------
   3) NEWS — 300 headlines/bodies per ticker, positive/negative/neutral.
   --------------------------------------------------------------------- */
TRUNCATE TABLE IF EXISTS RAW_NEWS;

INSERT INTO RAW_NEWS (record)
WITH g AS (
  SELECT
    UUID_STRING() AS news_id,
    GET(ARRAY_CONSTRUCT('AAPL','MSFT','NVDA','AMZN','TSLA','JPM','GS'),
        UNIFORM(0, 6, RANDOM()))::string AS ticker,
    DATEADD('day', -UNIFORM(0, 90, RANDOM()), CURRENT_TIMESTAMP())::timestamp_ntz AS ts0,
    UNIFORM(1, 3, RANDOM()) AS bucket,
    UNIFORM(1, 3, RANDOM()) AS tmpl,
    GET(ARRAY_CONSTRUCT('MarketPulse','The Ledger','Capital Wire','StreetSignal','FinDesk'),
        UNIFORM(0, 4, RANDOM()))::string AS source
  FROM TABLE(GENERATOR(ROWCOUNT => 300))
),
e AS (
  SELECT news_id, ticker, ts0, source,
    CASE
      WHEN bucket = 1 THEN
        CASE tmpl WHEN 1 THEN ticker || ' beats earnings, raises full-year guidance'
                  WHEN 2 THEN 'Analysts upgrade ' || ticker || ' on resilient demand'
                  ELSE ticker || ' unveils new product line to strong reviews' END
      WHEN bucket = 2 THEN
        CASE tmpl WHEN 1 THEN ticker || ' misses revenue, warns on slowing demand'
                  WHEN 2 THEN 'Regulators open probe into ' || ticker || ' practices'
                  ELSE ticker || ' cuts outlook as costs climb' END
      ELSE
        CASE tmpl WHEN 1 THEN ticker || ' to present at industry conference next week'
                  WHEN 2 THEN ticker || ' names new operating executive'
                  ELSE ticker || ' shares trade flat amid a mixed market' END
    END AS headline,
    CASE
      WHEN bucket = 1 THEN ticker || ' reported quarterly results above analyst expectations, '
             || 'driven by strong demand and expanding margins. Management raised guidance and '
             || 'announced an accelerated buyback, sending shares higher.'
      WHEN bucket = 2 THEN ticker || ' fell short of revenue estimates and warned that demand is '
             || 'softening into next quarter. Management flagged margin pressure and rising costs, '
             || 'and the stock dropped sharply after the report.'
      ELSE ticker || ' provided a routine business update with no change to financial guidance. '
             || 'Analysts viewed the news as neutral for the shares.'
    END AS body
  FROM g
)
SELECT OBJECT_CONSTRUCT(
  'news_id', news_id,
  'ts', TO_CHAR(ts0, 'YYYY-MM-DD"T"HH24:MI:SS'),
  'ticker', ticker,
  'headline', headline,
  'body', body,
  'source', source
)
FROM e;

-- ---- validation ----
SELECT 'RAW_MARKET' AS t, COUNT(*) AS n_rows FROM RAW_MARKET
UNION ALL SELECT 'RAW_TRANSACTIONS', COUNT(*) FROM RAW_TRANSACTIONS
UNION ALL SELECT 'RAW_NEWS', COUNT(*) FROM RAW_NEWS;
