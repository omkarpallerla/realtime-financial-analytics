"""
backfill_market.py — OPTIONAL one-time market history backfill
==============================================================
The in-cloud TASK only collects market data from the moment you turn it
on, so forecasting/anomaly need a head start. This pulls ~3 months of
DAILY candles from the same Yahoo endpoint and lands them in
BRONZE.RAW_MARKET in the identical JSON shape, so SILVER parses them the
same way. Run once before sql/07 and sql/08.

Usage:
  python ingest/backfill_market.py

Uses key-pair auth from config/.env (same as the Snowpipe lane).
"""
import os
import requests
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

TICKERS = [t.strip() for t in os.getenv("TICKERS", "AAPL,MSFT,NVDA,AMZN,TSLA,JPM,GS").split(",")]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RFAP/1.0"}


def _connect():
    pem = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).read_bytes()
    pk = serialization.load_pem_private_key(pem, password=None, backend=default_backend())
    der = pk.private_bytes(serialization.Encoding.DER,
                           serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption())
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=der,
        role=os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "RFAP_WH"),
        database="RFAP_DB", schema="BRONZE",
    )


def main():
    conn = _connect()
    cur = conn.cursor()
    n = 0
    for t in TICKERS:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
               f"?interval=1d&range=3mo")
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200 or not r.text:
            print(f"  {t}: HTTP {r.status_code} (skipped)")
            continue
        cur.execute(
            "INSERT INTO RFAP_DB.BRONZE.RAW_MARKET (ticker, payload, source) "
            "SELECT %s, PARSE_JSON(%s), 'yahoo_backfill'",
            (t, r.text),
        )
        n += 1
        print(f"  {t}: loaded 3mo of daily candles")
    cur.close(); conn.close()
    print(f"Backfilled {n}/{len(TICKERS)} tickers. "
          f"Now run sql/05 (rebuild silver), then 07/08.")


if __name__ == "__main__":
    main()
