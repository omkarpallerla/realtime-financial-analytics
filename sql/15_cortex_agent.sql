/* =====================================================================
   15_cortex_agent.sql  —  Cortex Agent (Analyst + Search in one bot)
   A Cortex Agent orchestrates MULTIPLE tools: it decides whether to
   answer with governed SQL (Cortex Analyst) or by retrieving news
   (Cortex Search), and can combine both. The agent is invoked from the
   Streamlit "AI Analyst Agent" tab via:
       POST /api/v2/cortex/agent:run
   This file just verifies the two tools the agent depends on exist;
   the agent's tool spec is assembled in streamlit/app.py.
   Run as ACCOUNTADMIN (after 10 + 14).
   ===================================================================== */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE RFAP_WH;
USE DATABASE RFAP_DB;
USE SCHEMA GOLD;

-- Tool 1: the Analyst semantic model (structured questions -> SQL).
LS @RFAP_SEMANTIC_STAGE;

-- Tool 2: the news RAG service (unstructured questions -> retrieval).
SHOW CORTEX SEARCH SERVICES LIKE 'RFAP_NEWS_SEARCH';

/* ---------------------------------------------------------------------
   The agent request the app sends looks like:

   {
     "model": "llama3.1-70b",
     "messages": [{"role":"user","content":[{"type":"text","text":"<question>"}]}],
     "tools": [
       {"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "finance_sql"}},
       {"tool_spec": {"type": "cortex_search", "name": "news_search"}}
     ],
     "tool_resources": {
       "finance_sql": {"semantic_model_file":
         "@RFAP_DB.GOLD.RFAP_SEMANTIC_STAGE/finance_semantic_model.yaml"},
       "news_search": {"name": "RFAP_DB.GOLD.RFAP_NEWS_SEARCH",
                       "max_results": 5}
     }
   }

   Ask it things that need BOTH data and news, e.g.:
     "Which stock fell most this week and what news explains it?"
   --------------------------------------------------------------------- */
