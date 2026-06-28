"""
silver_transform.py — Snowpark BRONZE -> SILVER (source of truth)
=================================================================
This is the same logic registered as the stored procedure
RFAP_DB.SILVER.BUILD_SILVER in sql/05_silver_snowpark.sql. Kept here so
the transformation lives in version control and can be run locally:

  python snowpark/silver_transform.py

(uses key-pair auth from config/.env). Inside Snowflake the SP calls
build_silver(session) with the active session.
"""
from snowflake.snowpark.functions import col, to_timestamp_ntz
from snowflake.snowpark.types import StringType, DoubleType, BooleanType


def build_silver(session) -> str:
    # MARKET: flatten Yahoo's nested OHLC arrays (SQL is cleanest for VARIANT).
    session.sql("""
      CREATE OR REPLACE TABLE RFAP_DB.SILVER.MARKET_PRICES AS
      SELECT
        m.payload:chart.result[0].meta.symbol::string                          AS TICKER,
        TO_TIMESTAMP_NTZ(ts.value::number)                                     AS TS,
        GET(m.payload:chart.result[0].indicators.quote[0].open,   ts.index)::float  AS OPEN,
        GET(m.payload:chart.result[0].indicators.quote[0].high,   ts.index)::float  AS HIGH,
        GET(m.payload:chart.result[0].indicators.quote[0].low,    ts.index)::float  AS LOW,
        GET(m.payload:chart.result[0].indicators.quote[0].close,  ts.index)::float  AS CLOSE,
        GET(m.payload:chart.result[0].indicators.quote[0].volume, ts.index)::number AS VOLUME,
        m.ingested_at
      FROM RFAP_DB.BRONZE.RAW_MARKET m,
           LATERAL FLATTEN(input => m.payload:chart.result[0].timestamp) ts
      WHERE GET(m.payload:chart.result[0].indicators.quote[0].close, ts.index) IS NOT NULL
      QUALIFY ROW_NUMBER() OVER (PARTITION BY TICKER, TS ORDER BY m.ingested_at DESC) = 1
    """).collect()

    # TRANSACTIONS: Snowpark DataFrame API.
    txn = (session.table("RFAP_DB.BRONZE.RAW_TRANSACTIONS").select(
        col("record")["txn_id"].cast(StringType()).alias("TXN_ID"),
        col("record")["account_id"].cast(StringType()).alias("ACCOUNT_ID"),
        to_timestamp_ntz(col("record")["ts"].cast(StringType())).alias("TXN_TS"),
        col("record")["amount"].cast(DoubleType()).alias("AMOUNT"),
        col("record")["category"].cast(StringType()).alias("CATEGORY"),
        col("record")["merchant"].cast(StringType()).alias("MERCHANT"),
        col("record")["city"].cast(StringType()).alias("CITY"),
        col("record")["country"].cast(StringType()).alias("COUNTRY"),
        col("record")["channel"].cast(StringType()).alias("CHANNEL"),
        col("record")["is_fraud"].cast(BooleanType()).alias("IS_FRAUD_LABEL"),
    ).drop_duplicates(["TXN_ID"]))
    txn.write.mode("overwrite").save_as_table("RFAP_DB.SILVER.TRANSACTIONS")

    # NEWS: Snowpark DataFrame API.
    news = (session.table("RFAP_DB.BRONZE.RAW_NEWS").select(
        col("record")["news_id"].cast(StringType()).alias("NEWS_ID"),
        to_timestamp_ntz(col("record")["ts"].cast(StringType())).alias("PUBLISHED_AT"),
        col("record")["ticker"].cast(StringType()).alias("TICKER"),
        col("record")["headline"].cast(StringType()).alias("HEADLINE"),
        col("record")["body"].cast(StringType()).alias("BODY"),
        col("record")["source"].cast(StringType()).alias("SOURCE"),
    ).drop_duplicates(["NEWS_ID"]))
    news.write.mode("overwrite").save_as_table("RFAP_DB.SILVER.NEWS_ARTICLES")

    mp = session.table("RFAP_DB.SILVER.MARKET_PRICES").count()
    return f"SILVER built: market={mp} txns={txn.count()} news={news.count()}"


if __name__ == "__main__":
    import os
    from pathlib import Path
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    from snowflake.snowpark import Session
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")
    pem = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).read_bytes()
    pk = serialization.load_pem_private_key(pem, None, default_backend())
    der = pk.private_bytes(serialization.Encoding.DER,
                           serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption())
    session = Session.builder.configs({
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "private_key": der,
        "role": os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "RFAP_WH"),
        "database": "RFAP_DB", "schema": "SILVER",
    }).create()
    print(build_silver(session))
    session.close()
