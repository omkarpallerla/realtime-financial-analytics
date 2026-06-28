# 📈 Real-Time Financial Analytics Platform

### A full, real-time fintech BI pipeline built **100% inside Snowflake** — Snowpipe + Tasks ingestion, a Snowpark medallion, the entire Cortex AI stack (forecasting, anomaly detection, fraud LLM, RAG, Text2SQL, an agent, embeddings), and a polished Streamlit dashboard.

> **The story:** Live market data and synthetic card-transaction data stream in,
> get refined through a Bronze → Silver → Gold medallion, and are turned into
> anomaly flags, forecasts, explainable fraud alerts, and a natural-language
> analytics app — with **zero data movement, no GPUs, and no spend beyond a
> Snowflake trial.**

![architecture](docs/architecture.svg)

---

## 🎯 What it does

| Capability | How |
|---|---|
| **Real-time ingestion** | Synthetic transactions via **Snowpipe** (REST); live market data via a **serverless Task + External Access Integration** calling Yahoo Finance every 5 min |
| **Transformation** | **Snowpark Python** medallion (Bronze→Silver→Gold), wired as an incremental **Stream/Task DAG** |
| **Anomaly detection** | `SNOWFLAKE.ML.ANOMALY_DETECTION` on daily spend + market volume |
| **Forecasting** | `SNOWFLAKE.ML.FORECAST` for spend (14d) and per-ticker prices (7d), with bands |
| **News sentiment** | `CORTEX.SENTIMENT` + `AI_CLASSIFY` + `SUMMARIZE` on financial news |
| **Explainable fraud** | `AI_CLASSIFY` flags suspicious txns; `CORTEX.COMPLETE` writes the *reason* + recommended action |
| **Vector similarity** | `EMBED_TEXT_768` + `VECTOR_COSINE_SIMILARITY` to find look-alike transactions |
| **AI aggregate insight** | `AI_AGG` summarizes thousands of rows into a few bullets |
| **RAG copilot** | **Cortex Search** over news for grounded answers |
| **Text2SQL** | **Cortex Analyst** over a semantic model |
| **AI Agent** | Routes between Analyst (SQL) and Search (news) and synthesizes |
| **Dashboard** | **Streamlit-in-Snowflake** + Plotly — KPI cards, candlesticks, donuts, heatmaps, fraud gauges, forecast bands, daily AI brief |

---

## 🏗️ Architecture

```
Yahoo API ─(External Access)─► Task (5 min) ─► Snowpark SP ─┐
                                                            ├─► BRONZE ─► SILVER ─► GOLD ─► Cortex AI ─► Streamlit
Faker txns ─► files ─► Snowpipe REST drip ──────────────────┘   (Snowpark medallion, Task DAG)
```

- **DB** `RFAP_DB` · **WH** `RFAP_WH` (XS, 60s auto-suspend) · schemas `BRONZE` / `SILVER` / `GOLD`.

---

## 📁 Repository structure

```
realtime-financial-analytics/
├── README.md
├── requirements.txt
├── config/.env.example
├── ingest/            transaction_generator · snowpipe_drip · news_generator · backfill_market
├── sql/               00–16 numbered worksheets + 99_cleanup
├── snowpark/          silver_transform.py · gold_transform.py  (source of truth for the SPs)
├── models/            finance_semantic_model.yaml  (Cortex Analyst)
├── streamlit/         app.py · ui.py · environment.yml
└── docs/              architecture.svg · runbook.md · linkedin_post.md
```

---

## 🚀 Run it

You need a **Snowflake trial** (Cortex-enabled region: AWS `us-west-2`/`us-east-1`
or Azure `east-us-2`). Follow **[docs/runbook.md](docs/runbook.md)** — it's the
exact click-by-click order. In short:

1. Run `sql/00`→`04` in Snowsight (foundation + market ingestion).
2. Locally: `pip install -r requirements.txt`, generate transactions + news, and
   stream them with the Snowpipe drip; optionally backfill market history.
3. Run `sql/05`→`16` (medallion + the full AI layer).
4. Upload `models/finance_semantic_model.yaml` to the semantic stage.
5. Create the Streamlit app (`streamlit/app.py` + `ui.py`, packages `plotly`,
   `altair`) and explore the eight tabs.

---

## 💸 Cost & cleanup
XS warehouse with 60s auto-suspend; AI runs on small candidate/sample sets. Expect
a few dollars of the $300 trial. **Tear everything down** with `sql/99_cleanup.sql`.

> **Data ethics:** market data comes from Yahoo's public endpoint; transactions
> and news are **synthetic** (generated locally). No private or scraped data.

---

## 🛠️ Built with
Snowflake Snowpipe · Tasks · External Access · Snowpark Python · Cortex
(ML Forecast, Anomaly Detection, LLM COMPLETE/SENTIMENT/SUMMARIZE, AI_CLASSIFY,
AI_AGG, Search, Analyst, Agent, EMBED_TEXT_768) · Streamlit-in-Snowflake · Plotly · Python (Faker).
