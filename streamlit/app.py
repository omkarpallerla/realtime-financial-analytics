"""
Real-Time Financial Analytics Platform — Streamlit-in-Snowflake
===============================================================
Paste app.py + ui.py into a Streamlit app in Snowsight
(Projects > Streamlit > +). Database RFAP_DB, schema GOLD, warehouse
RFAP_WH. Add packages plotly + altair via the Packages picker
(see streamlit/environment.yml).

Tabs:
  📈 Market   💳 Spend   🚨 Anomalies & Fraud   🔮 Forecast
  📰 News     🤖 AI Agent   💬 Ask in English   📋 Daily Brief
"""
import json
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import _snowflake
from snowflake.snowpark.context import get_active_session

import ui

st.set_page_config(page_title="Real-Time Financial Analytics",
                   page_icon="📈", layout="wide")
ui.inject_theme()
session = get_active_session()

SEARCH_SERVICE = "RFAP_DB.GOLD.RFAP_NEWS_SEARCH"
SEMANTIC_MODEL = "@RFAP_DB.GOLD.RFAP_SEMANTIC_STAGE/finance_semantic_model.yaml"
MODEL = "llama3.1-70b"


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


def ask_analyst(question: str) -> dict:
    body = {"semantic_model_file": SEMANTIC_MODEL,
            "messages": [{"role": "user",
                          "content": [{"type": "text", "text": question}]}]}
    resp = _snowflake.send_snow_api_request(
        "POST", "/api/v2/cortex/analyst/message", {}, {}, body, {}, 30000)
    return json.loads(resp["content"])


# ---------------------------------------------------------------------
# Header + tabs
# ---------------------------------------------------------------------
ui.hero("📈 Real-Time Financial Analytics Platform",
        "Live market + transaction data through a Snowflake medallion pipeline · "
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
        st.info("No market data yet — run sql/04 (and optionally "
                "ingest/backfill_market.py), then sql/05–06.")
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

        intra = q(f"""SELECT ts, open, high, low, close, volume
                      FROM RFAP_DB.GOLD.V_MARKET_INTRADAY
                      WHERE ticker = '{sel}' ORDER BY ts""")
        left, right = st.columns([3, 2])
        with left:
            st.subheader(f"{sel} · intraday candles")
            if intra.empty:
                st.caption("No intraday candles yet for this ticker.")
            else:
                fig = go.Figure(go.Candlestick(
                    x=intra["TS"], open=intra["OPEN"], high=intra["HIGH"],
                    low=intra["LOW"], close=intra["CLOSE"],
                    increasing_line_color=ui.GREEN, decreasing_line_color=ui.RED))
                fig.update_layout(xaxis_rangeslider_visible=False)
                st.plotly_chart(ui.style_fig(fig, 380, legend=False),
                                use_container_width=True)
        with right:
            st.subheader("Volume")
            if not intra.empty:
                vfig = go.Figure(go.Bar(x=intra["TS"], y=intra["VOLUME"],
                                        marker_color=ui.BLUE))
                st.plotly_chart(ui.style_fig(vfig, 380, legend=False),
                                use_container_width=True)

        st.divider()
        st.subheader("Daily returns heatmap")
        md = q("""SELECT ticker, trade_date, daily_return
                  FROM RFAP_DB.GOLD.MARKET_DAILY
                  WHERE daily_return IS NOT NULL ORDER BY trade_date""")
        if md.empty:
            st.caption("Needs a few days of history — run ingest/backfill_market.py.")
        else:
            pivot = md.pivot(index="TICKER", columns="TRADE_DATE", values="DAILY_RETURN")
            hfig = px.imshow(pivot, aspect="auto", color_continuous_midpoint=0,
                             color_continuous_scale=[ui.RED, ui.SURFACE, ui.GREEN])
            st.plotly_chart(ui.style_fig(hfig, 280, legend=False),
                            use_container_width=True)


# ======================================================================
# TAB 2 — SPEND
# ======================================================================
with tab_spend:
    k = q("SELECT * FROM RFAP_DB.GOLD.V_SPEND_KPIS")
    if k.empty or k.iloc[0]["SPEND_30D"] is None:
        st.info("No transactions yet — run the generator + Snowpipe drip, "
                "then sql/05–06.")
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
            dfig = px.pie(cat, names="CATEGORY", values="TOTAL_SPEND", hole=0.62,
                          color_discrete_sequence=px.colors.sequential.Teal)
            dfig.update_traces(textposition="outside", textinfo="percent+label")
            st.plotly_chart(ui.style_fig(dfig, 360, legend=False),
                            use_container_width=True)
        with c2:
            st.subheader("Spend trend by category")
            sc = q("""SELECT spend_date, category, total_spend
                      FROM RFAP_DB.GOLD.SPEND_BY_CATEGORY ORDER BY spend_date""")
            if not sc.empty:
                afig = px.area(sc, x="SPEND_DATE", y="TOTAL_SPEND", color="CATEGORY",
                               color_discrete_sequence=px.colors.qualitative.Set3)
                st.plotly_chart(ui.style_fig(afig, 360), use_container_width=True)

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
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=an["DAY"], y=an["UPPER_BOUND"], line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=an["DAY"], y=an["LOWER_BOUND"], fill="tonexty",
                                 fillcolor="rgba(47,129,247,.12)", line=dict(width=0),
                                 name="expected band"))
        fig.add_trace(go.Scatter(x=an["DAY"], y=an["ACTUAL_SPEND"], mode="lines",
                                 line=dict(color=ui.BLUE, width=2), name="actual"))
        pts = an[an["IS_ANOMALY"] == 1]
        fig.add_trace(go.Scatter(x=pts["DAY"], y=pts["ACTUAL_SPEND"], mode="markers",
                                 marker=dict(color=ui.RED, size=11, symbol="x"),
                                 name="anomaly"))
        st.plotly_chart(ui.style_fig(fig, 340), use_container_width=True)

    st.divider()
    st.subheader("💳 AI fraud detection")
    fraud = q("SELECT * FROM RFAP_DB.GOLD.V_FRAUD_FLAGGED")
    scored = q("SELECT ai_fraud_class, COUNT(*) AS n FROM RFAP_DB.GOLD.FRAUD_SCORED "
               "GROUP BY ai_fraud_class") if True else None
    g1, g2 = st.columns([1, 2])
    with g1:
        try:
            total = int(scored["N"].sum())
            susp = int(scored[scored["AI_FRAUD_CLASS"] == "Suspicious"]["N"].sum())
            pct = 100 * susp / total if total else 0
            gfig = go.Figure(go.Indicator(
                mode="gauge+number", value=pct,
                number={"suffix": "%"},
                title={"text": "Suspicious share"},
                gauge={"axis": {"range": [0, 100]},
                       "bar": {"color": ui.RED},
                       "steps": [{"range": [0, 33], "color": "rgba(22,199,132,.25)"},
                                 {"range": [33, 66], "color": "rgba(240,160,32,.25)"},
                                 {"range": [66, 100], "color": "rgba(234,57,67,.25)"}]}))
            st.plotly_chart(ui.style_fig(gfig, 260, legend=False),
                            use_container_width=True)
            st.caption(f"{susp} suspicious of {total} AI-reviewed candidates")
        except Exception:
            st.info("Run sql/11_cortex_fraud.sql to score fraud.")
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
with tab_fc:
    st.subheader("🔮 Spend forecast (next 14 days)")
    st.caption("SNOWFLAKE.ML.FORECAST with a 90% prediction interval.")
    hist = q("SELECT spend_date AS d, total_spend AS y FROM RFAP_DB.GOLD.V_SPEND_TREND")
    fc = q("SELECT * FROM RFAP_DB.GOLD.V_SPEND_FORECAST")
    if fc.empty:
        st.info("Run sql/08_cortex_forecast.sql first.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pd.to_datetime(hist["D"]), y=hist["Y"],
                                 mode="lines", line=dict(color=ui.BLUE), name="actual"))
        fig.add_trace(go.Scatter(x=pd.to_datetime(fc["FORECAST_DATE"]), y=fc["UPPER_BOUND"],
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=pd.to_datetime(fc["FORECAST_DATE"]), y=fc["LOWER_BOUND"],
                                 fill="tonexty", fillcolor="rgba(22,199,132,.15)",
                                 line=dict(width=0), name="90% interval"))
        fig.add_trace(go.Scatter(x=pd.to_datetime(fc["FORECAST_DATE"]), y=fc["FORECAST"],
                                 mode="lines", line=dict(color=ui.GREEN, dash="dash"),
                                 name="forecast"))
        st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)

    st.divider()
    st.subheader("Price forecast (next 7 days)")
    pf = q("SELECT * FROM RFAP_DB.GOLD.V_PRICE_FORECAST")
    if pf.empty:
        st.caption("Run sql/08 (needs market history from backfill_market.py).")
    else:
        t = st.selectbox("Ticker", sorted(pf["TICKER"].unique()), key="fc_ticker")
        sub = pf[pf["TICKER"] == t]
        recent = q(f"""SELECT trade_date AS d, close AS y FROM RFAP_DB.GOLD.MARKET_DAILY
                       WHERE ticker='{t}' ORDER BY trade_date""")
        pfig = go.Figure()
        pfig.add_trace(go.Scatter(x=pd.to_datetime(recent["D"]), y=recent["Y"],
                                  mode="lines", line=dict(color=ui.BLUE), name="actual"))
        pfig.add_trace(go.Scatter(x=pd.to_datetime(sub["FORECAST_DATE"]), y=sub["UPPER_BOUND"],
                                  line=dict(width=0), showlegend=False, hoverinfo="skip"))
        pfig.add_trace(go.Scatter(x=pd.to_datetime(sub["FORECAST_DATE"]), y=sub["LOWER_BOUND"],
                                  fill="tonexty", fillcolor="rgba(47,129,247,.15)",
                                  line=dict(width=0), name="90% interval"))
        pfig.add_trace(go.Scatter(x=pd.to_datetime(sub["FORECAST_DATE"]), y=sub["FORECAST"],
                                  mode="lines", line=dict(color=ui.AMBER, dash="dash"),
                                  name="forecast"))
        st.plotly_chart(ui.style_fig(pfig, 360), use_container_width=True)


# ======================================================================
# TAB 5 — NEWS
# ======================================================================
with tab_news:
    st.subheader("📰 News & sentiment")
    feed = q("SELECT * FROM RFAP_DB.GOLD.V_NEWS_FEED LIMIT 200")
    if feed.empty:
        st.info("Run news_generator.py + sql/09_cortex_news_ai.sql.")
    else:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("**Latest headlines**")
            for _, r in feed.head(12).iterrows():
                lab = r["SENTIMENT_LABEL"]
                kind = {"Positive": "pos", "Negative": "neg"}.get(lab, "neu")
                bk = {"Positive": "pos", "Negative": "neg"}.get(lab, "neu")
                st.markdown(
                    f'<div class="card {kind}"><div class="h">{r["TICKER"]} · '
                    f'{r["HEADLINE"]} {ui.badge(lab, bk)}</div>'
                    f'<div class="m">{r["SUMMARY"]}</div></div>',
                    unsafe_allow_html=True)
        with c2:
            st.markdown("**Sentiment mix**")
            dist = feed.groupby("SENTIMENT_LABEL").size().reset_index(name="n")
            cmap = {"Positive": ui.GREEN, "Negative": ui.RED, "Neutral": ui.MUTED}
            bfig = px.bar(dist, x="SENTIMENT_LABEL", y="n", color="SENTIMENT_LABEL",
                          color_discrete_map=cmap)
            st.plotly_chart(ui.style_fig(bfig, 260, legend=False),
                            use_container_width=True)

            st.markdown("**Price vs. news sentiment**")
            pvt_t = st.selectbox("Ticker", sorted(feed["TICKER"].unique()),
                                 key="news_ticker")
            pvs = q(f"""SELECT trade_date, close, avg_sentiment
                        FROM RFAP_DB.GOLD.V_PRICE_VS_SENTIMENT
                        WHERE ticker='{pvt_t}' ORDER BY trade_date""")
            if not pvs.empty:
                dfig = go.Figure()
                dfig.add_trace(go.Scatter(x=pd.to_datetime(pvs["TRADE_DATE"]),
                                          y=pvs["CLOSE"], name="close",
                                          line=dict(color=ui.BLUE)))
                dfig.add_trace(go.Scatter(x=pd.to_datetime(pvs["TRADE_DATE"]),
                                          y=pvs["AVG_SENTIMENT"], name="sentiment",
                                          line=dict(color=ui.AMBER), yaxis="y2"))
                dfig.update_layout(yaxis2=dict(overlaying="y", side="right",
                                               showgrid=False, range=[-1, 1]))
                st.plotly_chart(ui.style_fig(dfig, 280), use_container_width=True)


# ======================================================================
# TAB 6 — AI AGENT (orchestrates Analyst SQL + News RAG)
# ======================================================================
with tab_agent:
    st.subheader("🤖 AI Analyst Agent")
    st.caption("One bot, two tools: it queries the data (Cortex Analyst) AND "
               "retrieves news (Cortex Search), then synthesizes an answer.")
    st.write("Try:  `Which stock looks weakest and what news explains it?`  ·  "
             "`Summarize spend and any fraud risk this month.`")
    aq = st.text_input("Ask the agent", key="agent_q",
                       placeholder="e.g. What's driving the move in NVDA?")
    if st.button("Run agent", type="primary", key="agent_btn") and aq:
        data_df, news_hits, data_note = None, [], ""
        with st.spinner("Tool 1/2 · querying the data (Cortex Analyst)…"):
            try:
                res = ask_analyst(aq)
                content = res["message"]["content"]
                for item in content:
                    if item["type"] == "text":
                        data_note += item["text"] + " "
                sql_item = next((c for c in content if c["type"] == "sql"), None)
                if sql_item:
                    data_df = session.sql(sql_item["statement"]).to_pandas()
            except Exception as e:
                data_note = f"(Analyst unavailable: {e})"
        with st.spinner("Tool 2/2 · retrieving news (Cortex Search)…"):
            try:
                news_hits = search_news(aq, 5)
            except Exception:
                news_hits = []

        ctx = f"DATA FINDINGS: {data_note}\n"
        if data_df is not None and not data_df.empty:
            ctx += "TABLE:\n" + data_df.head(10).to_csv(index=False) + "\n"
        if news_hits:
            ctx += "NEWS:\n" + "\n".join(
                f"- ({h.get('ticker')}/{h.get('sentiment_label')}) {h.get('headline')}"
                for h in news_hits)

        with st.spinner("Synthesizing final answer…"):
            final = complete(
                "You are a financial analyst agent. Using the data findings and "
                "news below, answer the user's question concisely, cite numbers and "
                "specific headlines, and note any caveats.\n\n"
                f"QUESTION: {aq}\n\n{ctx}")
        st.markdown("### Answer")
        st.write(final)
        if data_df is not None and not data_df.empty:
            with st.expander("📊 Data the agent queried"):
                st.dataframe(data_df, use_container_width=True, hide_index=True)
        if news_hits:
            with st.expander(f"📰 News the agent retrieved ({len(news_hits)})"):
                st.dataframe(pd.DataFrame(news_hits), use_container_width=True,
                             hide_index=True)


# ======================================================================
# TAB 7 — ASK IN ENGLISH (Cortex Analyst Text2SQL)
# ======================================================================
with tab_analyst:
    st.subheader("💬 Ask business questions in plain English")
    st.caption("Cortex Analyst turns your question into governed SQL, runs it, "
               "and shows the result + the generated SQL.")
    st.write("Try:  `What did customers spend the most on?`  ·  "
             "`Which stock had the worst average daily return?`")
    nq = st.text_input("Your question", key="analyst_q",
                       placeholder="e.g. Total spend by category last month")
    if st.button("Ask", type="primary", key="analyst_btn") and nq:
        with st.spinner("Generating SQL and running it…"):
            try:
                result = ask_analyst(nq)
                content = result["message"]["content"]
                for item in content:
                    if item["type"] == "text":
                        st.markdown(item["text"])
                sql_item = next((c for c in content if c["type"] == "sql"), None)
                if sql_item:
                    gsql = sql_item["statement"]
                    df = session.sql(gsql).to_pandas()
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    if df.shape[1] == 2 and df.shape[0] > 1:
                        st.bar_chart(df, x=df.columns[0], y=df.columns[1])
                    with st.expander("🧾 Generated SQL"):
                        st.code(gsql, language="sql")
            except Exception as e:
                st.error(f"Analyst call failed: {e}")
                st.info("Run sql/14 and upload finance_semantic_model.yaml "
                        "to RFAP_SEMANTIC_STAGE.")


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
                st.info("Make sure tabs' underlying tables exist (run sql/06–16).")


st.divider()
st.caption("Built with Snowflake Snowpipe · Snowpark · Cortex (ML Forecast, "
           "Anomaly Detection, LLM, Search, Analyst, Agent, Embeddings) · "
           "Streamlit-in-Snowflake · Plotly.")
