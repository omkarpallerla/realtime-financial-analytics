"""
news_generator.py — synthetic financial news headlines + bodies
===============================================================
Produces realistic, varied financial news per ticker (positive / negative
/ neutral) across the last ~90 days so the Cortex sentiment, RAG search,
and AI-aggregate steps have meaningful text to work with.

Usage:
  python ingest/news_generator.py             # write a JSON file locally
  python ingest/news_generator.py push        # ALSO PUT + COPY into Snowflake

Without 'push', upload the file via Snowsight (Data > RFAP_DB > BRONZE >
Stages > NEWS_STAGE > +Files) then re-run the COPY block in sql/02_bronze.sql.
"""
import os
import sys
import json
import uuid
import random
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

random.seed(7)
TICKERS = [t.strip() for t in os.getenv("TICKERS", "AAPL,MSFT,NVDA,AMZN,TSLA,JPM,GS").split(",")]
N_ARTICLES = int(os.getenv("NEWS_ARTICLES", "300"))
BATCH_DIR = Path(os.getenv("BATCH_DIR", "ingest/_batches"))
SOURCES = ["MarketPulse", "The Ledger", "Capital Wire", "StreetSignal", "FinDesk"]

POSITIVE = [
    ("{t} beats earnings, raises full-year guidance",
     "{t} reported quarterly results above analyst expectations, driven by strong demand and expanding margins. Management raised guidance and announced an accelerated buyback, sending shares higher in pre-market trading."),
    ("Analysts upgrade {t} on resilient demand",
     "Several analysts upgraded {t} to a buy rating, citing durable demand and improving cash flow. Price targets were lifted as the company gains share in its core markets."),
    ("{t} unveils new product line to strong reviews",
     "{t} launched a new product line that reviewers praised for performance and value. Early pre-orders are tracking ahead of internal targets, suggesting a healthy upgrade cycle."),
]
NEGATIVE = [
    ("{t} misses revenue, warns on slowing demand",
     "{t} fell short of revenue estimates and warned that demand is softening into next quarter. Management flagged margin pressure and rising costs, and the stock dropped sharply after the report."),
    ("Regulators open probe into {t} practices",
     "Regulators opened an investigation into {t} over its business practices, raising the prospect of fines and operational changes. The uncertainty weighed on the shares as investors reassessed risk."),
    ("{t} cuts outlook as costs climb",
     "{t} lowered its outlook, citing higher input costs and weaker pricing power. Analysts trimmed estimates and several lowered their price targets following the update."),
]
NEUTRAL = [
    ("{t} to present at industry conference next week",
     "{t} will present at an upcoming industry conference, where management is expected to discuss strategy and the demand environment. No financial guidance is anticipated at the event."),
    ("{t} names new operating executive",
     "{t} announced a leadership appointment to oversee operations. The company said the change supports its long-term plans; analysts viewed the move as routine."),
    ("{t} shares trade flat amid mixed market",
     "{t} shares were little changed as broader markets traded mixed. Volume was in line with recent averages and there were no company-specific catalysts on the day."),
]


def make_article() -> dict:
    t = random.choice(TICKERS)
    bucket = random.choices([POSITIVE, NEGATIVE, NEUTRAL], weights=[0.4, 0.35, 0.25])[0]
    headline, body = random.choice(bucket)
    ts = datetime.now() - timedelta(days=random.randint(0, 90),
                                    hours=random.randint(0, 23))
    return {
        "news_id": str(uuid.uuid4()),
        "ts": ts.replace(microsecond=0).isoformat(),
        "ticker": t,
        "headline": headline.format(t=t),
        "body": body.format(t=t),
        "source": random.choice(SOURCES),
    }


def write_file() -> Path:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    records = [make_article() for _ in range(N_ARTICLES)]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BATCH_DIR / f"news_{stamp}.batch.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    print(f"Wrote {len(records)} news articles -> {path}")
    return path


def push(path: Path):
    """PUT the file to NEWS_STAGE and COPY into RAW_NEWS (key-pair auth)."""
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    pem = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).read_bytes()
    pk = serialization.load_pem_private_key(pem, password=None, backend=default_backend())
    der = pk.private_bytes(serialization.Encoding.DER,
                           serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption())
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=der,
        role=os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "RFAP_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "RFAP_DB"),
        schema="BRONZE",
    )
    uri = "file://" + str(path.resolve()).replace("\\", "/")
    cur = conn.cursor()
    cur.execute(f"PUT '{uri}' @RFAP_DB.BRONZE.NEWS_STAGE AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
    cur.execute("""
        COPY INTO RFAP_DB.BRONZE.RAW_NEWS (record)
        FROM (SELECT $1 FROM @RFAP_DB.BRONZE.NEWS_STAGE)
        FILE_FORMAT = (FORMAT_NAME = RFAP_DB.BRONZE.JSON_FMT)
        ON_ERROR = CONTINUE
    """)
    print("Pushed news into RFAP_DB.BRONZE.RAW_NEWS.")
    cur.close(); conn.close()


if __name__ == "__main__":
    p = write_file()
    if len(sys.argv) > 1 and sys.argv[1] == "push":
        push(p)
