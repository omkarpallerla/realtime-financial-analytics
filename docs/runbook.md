# Runbook — exact order to stand the platform up

Everything SQL runs in **Snowsight worksheets** (paste a file → *Run All*).
The two Python lanes run locally. Total Cortex/compute cost is a few dollars
of your $300 trial. Run `sql/99_cleanup.sql` when done.

## 0. One-time local setup (only needed for the Snowpipe + backfill lanes)
```powershell
cd C:\Users\omkar\Snowflake\realtime-financial-analytics
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config\.env.example config\.env     # then edit values
```
Generate an **RSA key pair** (Git Bash) and register the public key:
```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```
Point `SNOWFLAKE_PRIVATE_KEY_PATH` at `rsa_key.p8`, then in Snowsight run:
`ALTER USER <you> SET RSA_PUBLIC_KEY='<paste rsa_key.pub body, no headers/newlines>';`

## 1. Foundation (Snowsight)
| Step | File | Creates |
|---|---|---|
| 1 | `sql/00_setup.sql` | warehouse, DB, BRONZE/SILVER/GOLD, JSON format |
| 2 | `sql/01_external_access.sql` | network rule + EAI for Yahoo |
| 3 | `sql/02_bronze.sql` | raw tables + stages |
| 4 | `sql/03_snowpipe.sql` | the transactions PIPE (after registering your public key) |
| 5 | `sql/04_market_ingest_task.sql` | market SP + 5-min TASK (starts polling now) |

## 2. Get data in
1. **Market history (recommended, gives forecasting/anomaly a head start):**
   `python ingest/backfill_market.py`
2. **Transactions (Snowpipe):**
   ```powershell
   python ingest/transaction_generator.py        # 90-day history
   python ingest/snowpipe_drip.py                # stream into Snowflake
   # later, to demo "live": python transaction_generator.py live  &  snowpipe_drip.py watch
   ```
3. **News:** `python ingest/news_generator.py push`

## 3. Transform (Snowsight)
| Step | File |
|---|---|
| 6 | `sql/05_silver_snowpark.sql` (also wires the SILVER task) |
| 7 | `sql/06_gold_marts.sql` (finishes + resumes the market→silver→gold task DAG) |

## 4. AI layer (Snowsight)
| Step | File | Adds |
|---|---|---|
| 8  | `sql/07_cortex_anomaly.sql` | spend + volume anomaly detection |
| 9  | `sql/08_cortex_forecast.sql` | spend + price forecasts |
| 10 | `sql/09_cortex_news_ai.sql` | news sentiment / topic / summary |
| 11 | `sql/10_cortex_search.sql` | RAG search service |
| 12 | `sql/11_cortex_fraud.sql` | AI fraud class + LLM reasons |
| 13 | `sql/12_vector_similarity.sql` | embeddings + similar-txn function |
| 14 | `sql/13_ai_aggregate.sql` | AI_AGG insights |
| 15 | `sql/16_gold_views.sql` | app-facing views |
| 16 | `sql/14_cortex_analyst.sql` | semantic stage — then upload `models/finance_semantic_model.yaml` to `RFAP_SEMANTIC_STAGE` and re-run the `ALTER STAGE … REFRESH;` |
| 17 | `sql/15_cortex_agent.sql` | verifies the agent's two tools |

## 5. Launch the dashboard
1. Snowsight → **Projects → Streamlit → + Streamlit App** (DB `RFAP_DB`, schema
   `GOLD`, warehouse `RFAP_WH`).
2. In the editor **Packages** picker add `plotly` and `altair`.
3. Add a second file `ui.py`; paste `streamlit/ui.py`. Paste `streamlit/app.py`
   into the main file. **Run**.
4. Click through all eight tabs.

## Troubleshooting
- **Cortex function "not available in region":** trial Cortex works in AWS
  `us-west-2`/`us-east-1`, Azure `east-us-2`. Create the trial in one of those.
- **Market SP returns "No market data":** check `SHOW EXTERNAL ACCESS
  INTEGRATIONS` and that the network rule lists both Yahoo hosts.
- **Snowpipe rows don't appear:** `SELECT SYSTEM$PIPE_STATUS('RFAP_DB.BRONZE.RFAP_TXN_PIPE');`
  and confirm your `RSA_PUBLIC_KEY` is set and the private key path is correct.
- **Forecast/anomaly errors on too little data:** run `backfill_market.py` and
  the 90-day transaction history, then re-run `sql/05`,`06`,`07`,`08`.
- **Tasks not running:** `SHOW TASKS IN DATABASE RFAP_DB;` — all three should be
  `started`; resume order is gold → silver → market.
