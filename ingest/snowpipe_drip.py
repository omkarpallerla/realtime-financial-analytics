"""
snowpipe_drip.py — stream batch files into Snowflake via Snowpipe REST
======================================================================
For each new *.batch.json in BATCH_DIR:
  1) PUT it to the internal stage (TXN_STAGE) using key-pair auth
  2) notify the Snowpipe PIPE via the REST API (SimpleIngestManager)
  3) move it to BATCH_DIR/_done so it isn't re-sent

Usage:
  python ingest/snowpipe_drip.py            # process current files once
  python ingest/snowpipe_drip.py watch      # keep polling for new files

Prereqs: key-pair auth configured (see sql/03_snowpipe.sql) and config/.env
filled in. This is the authentic Snowpipe path — no cloud bucket needed.
"""
import os
import sys
import time
from pathlib import Path

import snowflake.connector
from snowflake.ingest import SimpleIngestManager, StagedFile
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

ACCOUNT = os.environ["SNOWFLAKE_ACCOUNT"]
USER = os.environ["SNOWFLAKE_USER"]
KEY_PATH = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
PIPE_FQN = os.getenv("PIPE_FQN", "RFAP_DB.BRONZE.RFAP_TXN_PIPE")
STAGE = os.getenv("TXN_STAGE", "@RFAP_DB.BRONZE.TXN_STAGE")
BATCH_DIR = Path(os.getenv("BATCH_DIR", "ingest/_batches"))
DONE_DIR = BATCH_DIR / "_done"

PEM = Path(KEY_PATH).read_bytes()
_private_key = serialization.load_pem_private_key(PEM, password=None,
                                                  backend=default_backend())
PKB_DER = _private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

ingest_mgr = SimpleIngestManager(
    account=ACCOUNT.split(".")[0],
    host=f"{ACCOUNT}.snowflakecomputing.com",
    user=USER,
    pipe=PIPE_FQN,
    private_key=PEM.decode("utf-8"),
)


def _connect():
    return snowflake.connector.connect(
        account=ACCOUNT,
        user=USER,
        private_key=PKB_DER,
        role=os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "RFAP_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "RFAP_DB"),
    )


def process_once(conn) -> int:
    files = sorted(p for p in BATCH_DIR.glob("*.batch.json"))
    if not files:
        return 0
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    cur = conn.cursor()
    staged = []
    for f in files:
        # forward slashes + file:// for the PUT command
        uri = "file://" + str(f.resolve()).replace("\\", "/")
        cur.execute(f"PUT '{uri}' {STAGE} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
        staged.append(StagedFile(f.name + ".gz", None))

    # Notify Snowpipe to load the freshly staged files.
    resp = ingest_mgr.ingest_files(staged)
    print(f"  Snowpipe response: {resp['responseCode']}  "
          f"({len(staged)} file(s))")

    for f in files:
        f.replace(DONE_DIR / f.name)
    cur.close()
    return len(files)


def main():
    watch = len(sys.argv) > 1 and sys.argv[1] == "watch"
    conn = _connect()
    try:
        if watch:
            print("Watching for new batches (Ctrl+C to stop)...")
            while True:
                n = process_once(conn)
                if n:
                    print(f"Streamed {n} batch file(s) at "
                          f"{time.strftime('%H:%M:%S')}")
                time.sleep(15)
        else:
            n = process_once(conn)
            print(f"Done. Streamed {n} batch file(s)." if n
                  else "No batch files found. Run transaction_generator.py first.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
