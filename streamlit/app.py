"""
Real-Time Financial Analytics Platform — Streamlit-in-Snowflake
===============================================================
Runs on trial Streamlit-in-Snowflake: charts use Altair (bundled), and
Text2SQL uses CORTEX.COMPLETE to generate SQL (no _snowflake module, no
External Access needed). Paste app.py + ui.py; database RFAP_DB, schema GOLD.

Tabs:
  📈 Market   💳 Spend   🚨 Anomalies & Fraud   🔮 Forecast
  📰 News     🤖 AI Agent   💬 Ask in English   📋 Daily Brief
"""
import json
import pandas as pd
import streamlit as st
import altair as alt
from snowflake.snowpark.context import get_active_session

import ui

st.set_page_config(page_title="Real-Time Financial Analytics",
                   page_icon="📈", layout="wide")
ui.inject_theme()
session = get_active_session()

SEARCH_SERVICE = "RFAP_DB.GOLD.RFAP_NEWS_SEARCH"
MODEL = "llama3.1-70b"

# Schema context for LLM-generated Text2SQL.
SCHEMA_DOC = """
Snowflake tables (use fully-qualified names):
RFAP_DB.GOLD.TXN_FEATURES(txn_id, account_id, txn_ts TIMESTAMP, amount FLOAT,
  category, merchant, city, country, channel, is_fraud_label BOOLEAN,
  txn_hour, amt_vs_cat_avg)  -- one row per card transaction
RFAP_DB.GOLD.SPEND_DAILY(spend_date DATE, txn_count, total_spend, avg_ticket)
RFAP_DB.GOLD.SPEND_BY_CATEGORY(spend_date DATE, category, txn_count, total_spend)
RFAP_DB.GOLD.MARKET_DAILY(ticker, trade_date DATE, open, high, low, close,
  volume, daily_return)  -- daily OHLC per stock ticker
RFAP_DB.GOLD.NEWS_ENRICHED(news_id, published_at TIMESTAMP, ticker, headline,
  body, sentiment_score FLOAT, sentiment_label, topic, summary)
Tickers: AAPL, MSFT, NVDA, AMZN, TSLA, JPM, GS.
"""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
@st.cache_data(ttl=120)
def q(sql: str) -> pd.DataFrame:
    return session.sql(sql).to_pandas()


def human(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    for unit in ["", "K", "M", "B"]:
        if abs(n) < 1000:
            return f"{n:,.0f}{unit}" if unit else f"{n:,.0f}"
        n /= 1000
    return f"{n:,.1f}T"


def theme(chart, height=320):
    return (chart.properties(height=height)
            .configure_view(strokeWidth=0)
            .configure_axis(grid=True, gridColor=ui.LINE, domainColor=ui.LINE,
                            labelColor=ui.MUTED, titleColor=ui.MUTED, tickColor=ui.LINE)
            .configure_legend(labelColor=ui.TEXT, titleColor=ui.MUTED)
            .configure(background="transparent"))


def complete(prompt: str) -> str:
    p = prompt.replace("'", "''")
    return session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{MODEL}', '{p}') AS A"
    ).collect()[0]["A"]


def search_news(query: str, limit: int = 5) -> list:
    payload = json.dumps({"query": query,
                          "columns": ["headline", "ticker", "sentiment_label", "body"],
                          "limit": limit})
    sql = (f"SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW('{SEARCH_SERVICE}', "
           f"'{payload.replace(chr(39), chr(39) * 2)}') AS R")
    raw = session.sql(sql).collect()[0]["R"]
    return json.loads(raw).get("results", [])


def gen_sql(question: str) -> str:
    """LLM Text2SQL: ask Cortex to write one Snowflake query for the question."""
    prompt = (
        "You are a Snowflake SQL expert. Using ONLY the schema below, write a "
        "single valid Snowflake SQL query that answers the question. Return ONLY "
        "the SQL — no explanation, no markdown code fences.\n\n"
        f"{SCHEMA_DOC}\nQUESTION: {question}\nSQL:")
    sql = complete(prompt)
    # strip code fences / stray labels the model sometimes adds
    sql = sql.replace("```sql", "").replace("```", "").strip()
    if sql.lower().startswith("sql"):
        sql = sql[3:].strip()
    return sql.rstrip(";")


def run_text2sql(question: str):
    sql = gen_sql(question)
    df = session.sql(sql).to_pandas()
    return sql, df


# ---------------------------------------------------------------------
# Header + tabs
# ---------------------------------------------------------------------
ui.hero("📈 Real-Time Financial Analytics Platform",
        "Market + transaction data through a Snowflake medallion pipeline · "
        "Cortex anomaly detection, forecasting, fraud AI, RAG & Text2SQL.")

(tab_mkt, tab_spend, tab_fraud, tab_fc, tab_news,
 tab_agent, tab_analyst, tab_brief) = st.tabs(
    ["📈 Market", "💳 Spend", "🚨 Anomalies & Fraud", "🔮 Forecast",
     "📰 News", "🤖 AI Agent", "💬 Ask in English", "📋 Daily Brief"])


# ======================================================================
# TAB 1 — MARKET
# ======================================================================
with tab_mkt:
    latest = q("SELECT * FROM RFAP_DB.GOLD.V_MARKET_LATEST")
    if latest.empty:
        st.info("No market data yet.")
    else:
        tickers = sorted(latest["TICKER"].dropna().tolist())
        sel = st.selectbox("Ticker", tickers, key="mkt_ticker")
        row = latest[latest["TICKER"] == sel].iloc[0]
        up = (row["DAY_CHANGE_PCT"] or 0) >= 0
        n_up = int((latest["DAY_CHANGE_PCT"].fillna(0) >= 0).sum())
        ui.kpi_row([
            {"label": f"{sel} last price", "value": f"${row['LAST_PRICE']:,.2f}",
             "delta": f"{row['DAY_CHANGE']:+.2f} ({row['DAY_CHANGE_PCT']:+.2f}%)",
             "positive": up},
            {"label": "Last volume", "value": human(row["LAST_VOLUME"])},
            {"label": "Tickers up today", "value": f"{n_up} / {len(latest)}",
             "positive": n_up >= len(latest) / 2, "delta": "advancers"},
            {"label": "As of", "value": str(row["AS_OF"])[:16], "sub": "exchange time"},
        ])
        st.write("")

        candles = q(f"""SELECT trade_date, open, high, low, close, volume
                        FROM RFAP_DB.GOLD.MARKET_DAILY
                        WHERE ticker = '{sel}' ORDER BY trade_date""")
        if not candles.empty:
            candles["TRADE_DATE"] = pd.to_datetime(candles["TRADE_DATE"])
            st.subheader(f"{sel} · daily candles")
            color = alt.condition("datum.OPEN <= datum.CLOSE",
                                  alt.value(ui.GREEN), alt.value(ui.RED))
            base = alt.Chart(candles).encode(x=alt.X("TRADE_DATE:T", title=None))
            wick = base.mark_rule().encode(y="LOW:Q", y2="HIGH:Q", color=color)
            body = base.mark_bar(size=5).encode(
                y=alt.Y("OPEN:Q", title="price", scale=alt.Scale(zero=False)),
                y2="CLOSE:Q", color=color)
            st.altair_chart(theme(wick + body, 340), use_container_width=True)
            vol = alt.Chart(candles).mark_bar(color=ui.BLUE, opacity=0.6).encode(
                x=alt.X("TRADE_DATE:T", title=None), y=alt.Y("VOLUME:Q", title="volume"))
            st.altair_chart(theme(vol, 130), use_container_width=True)

        st.divider()
        st.subheader("Daily returns heatmap")
        md = q("""SELECT ticker, trade_date, daily_return
                  FROM RFAP_DB.GOLD.MARKET_DAILY
                  WHERE daily_return IS NOT NULL ORDER BY trade_date""")
        if not md.empty:
            md["TRADE_DATE"] = pd.to_datetime(md["TRADE_DATE"])
            hm = alt.Chart(md).mark_rect().encode(
                x=alt.X("TRADE_DATE:T", title=None, axis=alt.Axis(labels=False, ticks=False)),
                y=alt.Y("TICKER:N", title=None),
                color=alt.Color("DAILY_RETURN:Q",
                                scale=alt.Scale(scheme="redyellowgreen", domainMid=0),
                                legend=alt.Legend(title="return")))
            st.altair_chart(theme(hm, 240), use_container_width=True)


# ======================================================================
# TAB 2 — SPEND
# ======================================================================
with tab_spend:
    k = q("SELECT * FROM RFAP_DB.GOLD.V_SPEND_KPIS")
    if k.empty or k.iloc[0]["SPEND_30D"] is None:
        st.info("No transactions yet.")
    else:
        k = k.iloc[0]
        mom = k["SPEND_MOM_PCT"] or 0
        ui.kpi_row([
            {"label": "Spend (30d)", "value": f"${human(k['SPEND_30D'])}",
             "delta": f"{mom:+.1f}", "delta_is_pct": True, "positive": mom >= 0,
             "sub": "vs prior 30d"},
            {"label": "Transactions (30d)", "value": human(k["TXNS_30D"])},
            {"label": "Avg ticket", "value": f"${k['AVG_TICKET_30D']:,.2f}"},
            {"label": "Daily avg", "value": f"${human((k['SPEND_30D'] or 0)/30)}"},
        ])
        st.write("")
        c1, c2 = st.columns([2, 3])
        with c1:
            st.subheader("Spend by category (30d)")
            cat = q("SELECT * FROM RFAP_DB.GOLD.V_CATEGORY_SHARE")
            donut = alt.Chart(cat).mark_arc(innerRadius=65).encode(
                theta="TOTAL_SPEND:Q",
                color=alt.Color("CATEGORY:N", legend=alt.Legend(title=None)),
                tooltip=["CATEGORY", "TOTAL_SPEND"])
            st.altair_chart(theme(donut, 340), use_container_width=True)
        with c2:
            st.subheader("Spend trend by category")
            sc = q("""SELECT spend_date, category, total_spend
                      FROM RFAP_DB.GOLD.SPEND_BY_CATEGORY ORDER BY spend_date""")
            if not sc.empty:
                sc["SPEND_DATE"] = pd.to_datetime(sc["SPEND_DATE"])
                area = alt.Chart(sc).mark_area().encode(
                    x=alt.X("SPEND_DATE:T", title=None),
                    y=alt.Y("TOTAL_SPEND:Q", stack="zero", title="spend"),
                    color=alt.Color("CATEGORY:N", legend=alt.Legend(title=None)))
                st.altair_chart(theme(area, 340), use_container_width=True)

        st.divider()
        st.subheader("🧠 AI spending insight")
        st.caption("AI_AGG summarizes thousands of transactions into a few bullets.")
        with st.spinner("Summarizing recent spend with AI_AGG…"):
            try:
                ins = q("SELECT insight FROM RFAP_DB.GOLD.V_AI_SPEND_INSIGHT")
                st.markdown(f'<div class="card pos"><div class="m">'
                            f'{ins.iloc[0]["INSIGHT"]}</div></div>',
                            unsafe_allow_html=True)
            except Exception as e:
                st.caption(f"Run sql/13_ai_aggregate.sql to enable this. ({e})")


# ======================================================================
# TAB 3 — ANOMALIES & FRAUD
# ======================================================================
with tab_fraud:
    st.subheader("🚨 Spend anomalies")
    st.caption("SNOWFLAKE.ML.ANOMALY_DETECTION flags days outside the expected band.")
    an = q("SELECT * FROM RFAP_DB.GOLD.V_SPEND_ANOMALIES")
    if an.empty:
        st.info("Run sql/07_cortex_anomaly.sql first.")
    else:
        an["DAY"] = pd.to_datetime(an["DAY"])
        band = alt.Chart(an).mark_area(opacity=0.15, color=ui.BLUE).encode(
            x=alt.X("DAY:T", title=None), y="LOWER_BOUND:Q", y2="UPPER_BOUND:Q")
        line = alt.Chart(an).mark_line(color=ui.BLUE).encode(
            x="DAY:T", y=alt.Y("ACTUAL_SPEND:Q", title="spend"))
        pts = alt.Chart(an[an["IS_ANOMALY"] == 1]).mark_point(
            color=ui.RED, size=90, shape="cross", filled=True).encode(
            x="DAY:T", y="ACTUAL_SPEND:Q", tooltip=["DAY", "ACTUAL_SPEND"])
        st.altair_chart(theme(band + line + pts, 320), use_container_width=True)

    st.divider()
    st.subheader("💳 AI fraud detection")
    fraud = q("SELECT * FROM RFAP_DB.GOLD.V_FRAUD_FLAGGED")
    try:
        scored = q("SELECT ai_fraud_class, COUNT(*) AS n FROM RFAP_DB.GOLD.FRAUD_SCORED "
                   "GROUP BY ai_fraud_class")
        total = int(scored["N"].sum())
        susp = int(scored[scored["AI_FRAUD_CLASS"] == "Suspicious"]["N"].sum())
        pct = 100 * susp / total if total else 0
    except Exception:
        scored, total, susp, pct = None, 0, 0, 0

    g1, g2 = st.columns([1, 2])
    with g1:
        ui.kpi_row([{"label": "Suspicious share", "value": f"{pct:.0f}%",
                     "positive": pct < 33, "delta": f"{susp} of {total} reviewed"}])
        if scored is not None and not scored.empty:
            bar = alt.Chart(scored).mark_bar().encode(
                x=alt.X("N:Q", title=None), y=alt.Y("AI_FRAUD_CLASS:N", title=None),
                color=alt.Color("AI_FRAUD_CLASS:N", legend=None,
                                scale=alt.Scale(domain=["Legitimate", "Suspicious"],
                                                range=[ui.GREEN, ui.RED])))
            st.altair_chart(theme(bar, 130), use_container_width=True)
    with g2:
        st.markdown("**Flagged transactions — with the LLM's reasoning**")
        if fraud.empty:
            st.caption("No flagged transactions yet (run sql/11).")
        for _, r in fraud.head(6).iterrows():
            st.markdown(
                f'<div class="card neg"><div class="h">${r["AMOUNT"]:,.2f} · '
                f'{r["CATEGORY"]} · {r["MERCHANT"]} '
                f'({r["CITY"]}, {r["COUNTRY"]}) {ui.badge(str(r["X_USUAL"])+"x usual","warn")}'
                f'</div><div class="m">{r["AI_REASON"]}</div></div>',
                unsafe_allow_html=True)

    if not fraud.empty:
        st.divider()
        st.subheader("🔎 Look-alike transactions (vector similarity)")
        st.caption("EMBED_TEXT_768 + VECTOR_COSINE_SIMILARITY find similar txns.")
        tid = st.selectbox("Flagged transaction", fraud["TXN_ID"].tolist())
        if st.button("Find similar", key="sim"):
            try:
                sim = q(f"SELECT * FROM TABLE(RFAP_DB.GOLD.SIMILAR_TXNS('{tid}'))")
                st.dataframe(sim, use_container_width=True, hide_index=True)
            except Exception as e:
                st.caption(f"Run sql/12_vector_similarity.sql first. ({e})")


# ======================================================================
# TAB 4 — FORECAST
# ======================================================================
def forecast_chart(hist, fc, hist_x, hist_y, fx, actual_color, fc_color):
    h = alt.Chart(hist).mark_line(color=actual_color).encode(
        x=alt.X(f"{hist_x}:T", title=None),
        y=alt.Y(f"{hist_y}:Q", title=None, scale=alt.Scale(zero=False)))
    bandc = alt.Chart(fc).mark_area(opacity=0.18, color=fc_color).encode(
        x=alt.X(f"{fx}:T"), y="LOWER_BOUND:Q", y2="UPPER_BOUND:Q")
    fcl = alt.Chart(fc).mark_line(color=fc_color, strokeDash=[5, 4]).encode(
        x=f"{fx}:T", y="FORECAST:Q")
    return theme(h + bandc + fcl, 340)


with tab_fc:
    st.subheader("🔮 Spend forecast (next 14 days)")
    st.caption("SNOWFLAKE.ML.FORECAST with a 90% prediction interval.")
    hist = q("SELECT spend_date AS d, total_spend AS y FROM RFAP_DB.GOLD.V_SPEND_TREND")
    fc = q("SELECT * FROM RFAP_DB.GOLD.V_SPEND_FORECAST")
    if fc.empty:
        st.info("Run sql/08_cortex_forecast.sql first.")
    else:
        hist["D"] = pd.to_datetime(hist["D"])
        fc["FORECAST_DATE"] = pd.to_datetime(fc["FORECAST_DATE"])
        st.altair_chart(forecast_chart(hist, fc, "D", "Y", "FORECAST_DATE",
                        ui.BLUE, ui.GREEN), use_container_width=True)

    st.divider()
    st.subheader("Price forecast (next 7 days)")
    pf = q("SELECT * FROM RFAP_DB.GOLD.V_PRICE_FORECAST")
    if pf.empty:
        st.caption("Run sql/08.")
    else:
        t = st.selectbox("Ticker", sorted(pf["TICKER"].unique()), key="fc_ticker")
        sub = pf[pf["TICKER"] == t].copy()
        sub["FORECAST_DATE"] = pd.to_datetime(sub["FORECAST_DATE"])
        recent = q(f"""SELECT trade_date AS d, close AS y FROM RFAP_DB.GOLD.MARKET_DAILY
                       WHERE ticker='{t}' ORDER BY trade_date""")
        recent["D"] = pd.to_datetime(recent["D"])
        st.altair_chart(forecast_chart(recent, sub, "D", "Y", "FORECAST_DATE",
                        ui.BLUE, ui.AMBER), use_container_width=True)


# ======================================================================
# TAB 5 — NEWS
# ======================================================================
with tab_news:
    st.subheader("📰 News & sentiment")
    feed = q("SELECT * FROM RFAP_DB.GOLD.V_NEWS_FEED LIMIT 200")
    if feed.empty:
        st.info("Run sql/09_cortex_news_ai.sql.")
    else:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("**Latest headlines**")
            for _, r in feed.head(12).iterrows():
                lab = r["SENTIMENT_LABEL"]
                kind = {"Positive": "pos", "Negative": "neg"}.get(lab, "neu")
                st.markdown(
                    f'<div class="card {kind}"><div class="h">{r["TICKER"]} · '
                    f'{r["HEADLINE"]} {ui.badge(lab, kind)}</div>'
                    f'<div class="m">{r["SUMMARY"]}</div></div>',
                    unsafe_allow_html=True)
        with c2:
            st.markdown("**Sentiment mix**")
            dist = feed.groupby("SENTIMENT_LABEL").size().reset_index(name="n")
            bar = alt.Chart(dist).mark_bar().encode(
                x=alt.X("SENTIMENT_LABEL:N", title=None), y=alt.Y("n:Q", title=None),
                color=alt.Color("SENTIMENT_LABEL:N", legend=None,
                    scale=alt.Scale(domain=["Positive", "Neutral", "Negative"],
                                    range=[ui.GREEN, ui.MUTED, ui.RED])))
            st.altair_chart(theme(bar, 240), use_container_width=True)

            st.markdown("**Price vs. news sentiment**")
            pvt_t = st.selectbox("Ticker", sorted(feed["TICKER"].unique()),
                                 key="news_ticker")
            pvs = q(f"""SELECT trade_date, close, avg_sentiment
                        FROM RFAP_DB.GOLD.V_PRICE_VS_SENTIMENT
                        WHERE ticker='{pvt_t}' ORDER BY trade_date""")
            if not pvs.empty:
                pvs["TRADE_DATE"] = pd.to_datetime(pvs["TRADE_DATE"])
                base = alt.Chart(pvs).encode(x=alt.X("TRADE_DATE:T", title=None))
                price = base.mark_line(color=ui.BLUE).encode(
                    y=alt.Y("CLOSE:Q", title="close", scale=alt.Scale(zero=False)))
                sent = base.mark_line(color=ui.AMBER).encode(
                    y=alt.Y("AVG_SENTIMENT:Q", title="sentiment"))
                st.altair_chart(theme(alt.layer(price, sent).resolve_scale(y="independent"),
                                      260), use_container_width=True)


# ======================================================================
# TAB 6 — AI AGENT (Text2SQL + News RAG, synthesized)
# ======================================================================
with tab_agent:
    st.subheader("🤖 AI Analyst Agent")
    st.caption("One bot, two tools: it writes SQL to query the data AND retrieves "
               "news (Cortex Search), then synthesizes an answer.")
    st.write("Try:  `Which stock had the worst return and what news explains it?`  ·  "
             "`Summarize spend by category and any fraud risk.`")
    aq = st.text_input("Ask the agent", key="agent_q",
                       placeholder="e.g. What's the spending trend and news on NVDA?")
    if st.button("Run agent", type="primary", key="agent_btn") and aq:
        data_df, news_hits, gsql = None, [], ""
        with st.spinner("Tool 1/2 · writing + running SQL…"):
            try:
                gsql, data_df = run_text2sql(aq)
            except Exception as e:
                gsql = f"-- SQL tool failed: {e}"
        with st.spinner("Tool 2/2 · retrieving news (Cortex Search)…"):
            try:
                news_hits = search_news(aq, 5)
            except Exception:
                news_hits = []

        ctx = ""
        if data_df is not None and not data_df.empty:
            ctx += "DATA (from generated SQL):\n" + data_df.head(10).to_csv(index=False) + "\n"
        if news_hits:
            ctx += "NEWS:\n" + "\n".join(
                f"- ({h.get('ticker')}/{h.get('sentiment_label')}) {h.get('headline')}"
                for h in news_hits)

        with st.spinner("Synthesizing final answer…"):
            final = complete(
                "You are a financial analyst agent. Using the data and news below, "
                "answer the question concisely, cite numbers and specific headlines, "
                "and note caveats.\n\n"
                f"QUESTION: {aq}\n\n{ctx}")
        st.markdown("### Answer")
        st.write(final)
        if data_df is not None and not data_df.empty:
            with st.expander("📊 Data the agent queried"):
                st.dataframe(data_df, use_container_width=True, hide_index=True)
        if gsql:
            with st.expander("🧾 SQL the agent wrote"):
                st.code(gsql, language="sql")
        if news_hits:
            with st.expander(f"📰 News the agent retrieved ({len(news_hits)})"):
                st.dataframe(pd.DataFrame(news_hits), use_container_width=True,
                             hide_index=True)


# ======================================================================
# TAB 7 — ASK IN ENGLISH (LLM Text2SQL)
# ======================================================================
with tab_analyst:
    st.subheader("💬 Ask business questions in plain English")
    st.caption("Cortex COMPLETE turns your question into Snowflake SQL, runs it, "
               "and shows the result + the generated SQL.")
    st.write("Try:  `What did customers spend the most on?`  ·  "
             "`Which stock had the worst average daily return?`  ·  "
             "`Total spend by category`")
    nq = st.text_input("Your question", key="analyst_q",
                       placeholder="e.g. Average daily spend last week")
    if st.button("Ask", type="primary", key="analyst_btn") and nq:
        with st.spinner("Generating SQL and running it…"):
            try:
                gsql, df = run_text2sql(nq)
                st.dataframe(df, use_container_width=True, hide_index=True)
                if df.shape[1] == 2 and df.shape[0] > 1:
                    xcol, ycol = df.columns[0], df.columns[1]
                    ch = alt.Chart(df).mark_bar(color=ui.BLUE).encode(
                        x=alt.X(f"{xcol}:N", sort="-y", title=None),
                        y=alt.Y(f"{ycol}:Q", title=None))
                    st.altair_chart(theme(ch, 300), use_container_width=True)
                with st.expander("🧾 Generated SQL"):
                    st.code(gsql, language="sql")
            except Exception as e:
                st.error(f"Couldn't answer that one: {e}")
                st.caption("Try rephrasing — the model writes SQL against the GOLD tables.")


# ======================================================================
# TAB 8 — DAILY AI BRIEF
# ======================================================================
with tab_brief:
    st.subheader("📋 Daily AI market & risk brief")
    st.caption("Cortex COMPLETE writes an executive brief from today's KPIs, "
               "top movers, flagged fraud, and news themes.")
    if st.button("Generate brief", type="primary"):
        with st.spinner("Gathering signals and writing the brief…"):
            try:
                movers = q("""SELECT ticker, ROUND(day_change_pct,2) AS pct
                              FROM RFAP_DB.GOLD.V_MARKET_LATEST
                              ORDER BY day_change_pct DESC""")
                spend = q("SELECT * FROM RFAP_DB.GOLD.V_SPEND_KPIS").iloc[0]
                nflag = q("SELECT COUNT(*) AS n FROM RFAP_DB.GOLD.V_FRAUD_FLAGGED").iloc[0]["N"]
                themes = q("SELECT ticker, narrative FROM RFAP_DB.GOLD.V_AI_NEWS_THEMES")
                top = movers.head(3).to_dict("records")
                bot = movers.tail(3).to_dict("records")
                theme_txt = "\n".join(f"- {r['TICKER']}: {r['NARRATIVE']}"
                                      for _, r in themes.head(5).iterrows())
                prompt = (
                    "Write a concise daily brief (markdown, ~150 words) for a bank BI "
                    "team. Sections: Markets, Spending, Risk. Be specific with numbers.\n\n"
                    f"Top gainers: {top}\nTop losers: {bot}\n"
                    f"30d spend: ${spend['SPEND_30D']:,.0f}, MoM {spend['SPEND_MOM_PCT']:.1f}%\n"
                    f"Flagged fraud transactions: {nflag}\n"
                    f"News themes:\n{theme_txt}")
                st.markdown(complete(prompt))
            except Exception as e:
                st.error(f"Couldn't build the brief: {e}")


st.divider()
st.caption("Built with Snowflake Snowpipe · Snowpark · Cortex (ML Forecast, "
           "Anomaly Detection, LLM, Search, Text2SQL, Embeddings) · "
           "Streamlit-in-Snowflake · Altair.")
