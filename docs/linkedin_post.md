# LinkedIn post (paste-ready)

🏦 I built a **Real-Time Financial Analytics Platform** — entirely inside Snowflake.

Live market data + synthetic card transactions flow through a real-time pipeline
and come out the other side as an AI-powered fintech dashboard. No external
servers, no GPUs, no extra spend.

**The stack, end to end:**
🔹 **Ingestion** — Snowpipe streams transactions; a serverless Task + External
Access Integration pulls live market data from Yahoo every 5 minutes.
🔹 **Transformation** — Snowpark Python medallion (Bronze → Silver → Gold),
orchestrated as an incremental Task DAG.
🔹 **AI (Cortex)** — anomaly detection on spend, time-series forecasting for
prices & spend, news sentiment, **AI fraud detection that explains itself in
plain English**, vector-embedding similarity search, and AI_AGG insight summaries.
🔹 **GenAI querying** — a Text2SQL interface (Cortex Analyst) and an **AI Agent**
that combines SQL + news retrieval (RAG) to answer questions.
🔹 **Visualization** — a Streamlit dashboard: live KPI cards, candlesticks,
fraud-risk gauges, forecast bands, and a daily AI brief.

The part I'm proudest of: the AI doesn't just flag a suspicious transaction — it
writes *why* it's suspicious and recommends an action. That's the difference
between a model output and a decision a fraud team can act on.

This is the full stack a BI Analyst / BI Administrator at a fintech or bank
actually owns — ingestion, transformation, AI, and self-serve analytics, all in
one governed platform.

#Snowflake #Cortex #DataEngineering #FinTech #AI #Snowpark #Streamlit

---

## Talking points (for interviews)
- **Why medallion?** Raw is immutable/auditable; Silver is the clean contract;
  Gold is business-ready — each layer has one job, which makes the pipeline
  debuggable and incremental.
- **Why in-database AI?** Zero data movement, governance stays intact, and there's
  no model-serving infra to run. Cortex gives LLMs, forecasting, anomaly detection,
  vector search, and Text2SQL as SQL functions.
- **The agent vs. the chatbot:** the Text2SQL tab answers structured questions;
  the agent *routes* — it queries the marts AND retrieves news, then synthesizes.
- **Cost control:** XS warehouse with 60s auto-suspend; AI runs on small candidate
  sets (top-N riskiest txns, a sampled embedding pool) — pennies, not dollars.
