"""
transaction_generator.py — synthetic credit-card transactions
==============================================================
Generates realistic card spend across categories and writes JSON batch
files into BATCH_DIR. snowpipe_drip.py then streams them into Snowflake.

Usage:
  python ingest/transaction_generator.py            # 90-day history backfill
  python ingest/transaction_generator.py live       # one fresh batch (now)
  python ingest/transaction_generator.py live 5     # 5 fresh batches

Each record carries an is_fraud label; a small % are injected with
anomalous patterns (foreign online spend, odd hours, amount spikes) so
the AI fraud/anomaly steps have something real to catch.
"""
import os
import sys
import json
import uuid
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from faker import Faker
except ImportError:
    raise SystemExit("Install deps first:  pip install -r requirements.txt")

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

fake = Faker()
Faker.seed(42)
random.seed(42)

BATCH_DIR = Path(os.getenv("BATCH_DIR", "ingest/_batches"))
TXN_PER_BATCH = int(os.getenv("TXN_PER_BATCH", "500"))
FRAUD_RATE = float(os.getenv("FRAUD_RATE", "0.02"))
N_ACCOUNTS = 200

# category -> (weight, (min_amount, max_amount))
CATEGORIES = {
    "Groceries":     (0.22, (8, 180)),
    "Dining":        (0.18, (10, 120)),
    "Shopping":      (0.15, (15, 400)),
    "Transport":     (0.12, (3, 60)),
    "Utilities":     (0.08, (40, 300)),
    "Entertainment": (0.08, (10, 90)),
    "Travel":        (0.07, (80, 1500)),
    "Health":        (0.06, (15, 500)),
    "Electronics":   (0.04, (50, 2500)),
}
CATS = list(CATEGORIES.keys())
CAT_WEIGHTS = [CATEGORIES[c][0] for c in CATS]

ACCOUNTS = [f"ACCT{1000 + i}" for i in range(N_ACCOUNTS)]
HOME_CITY = {a: fake.city() for a in ACCOUNTS}


def _amount(cat: str) -> float:
    lo, hi = CATEGORIES[cat][1]
    # log-ish skew toward smaller amounts
    return round(random.triangular(lo, hi, lo + (hi - lo) * 0.3), 2)


def make_txn(ts: datetime) -> dict:
    account = random.choice(ACCOUNTS)
    is_fraud = random.random() < FRAUD_RATE
    category = random.choices(CATS, weights=CAT_WEIGHTS, k=1)[0]

    if is_fraud:
        # anomalous: pricey, online, foreign, odd hour
        category = random.choice(["Electronics", "Shopping", "Travel"])
        amount = round(random.uniform(800, 5000), 2)
        channel = "online"
        country = random.choice(["NG", "RU", "CN", "BR", "RO"])
        city = fake.city()
        ts = ts.replace(hour=random.randint(1, 4))
    else:
        amount = _amount(category)
        channel = random.choices(["in_store", "online"], weights=[0.65, 0.35])[0]
        country = "US"
        city = HOME_CITY[account] if channel == "in_store" else fake.city()

    return {
        "txn_id": str(uuid.uuid4()),
        "account_id": account,
        "ts": ts.replace(tzinfo=None).isoformat(timespec="seconds"),
        "amount": amount,
        "category": category,
        "merchant": fake.company(),
        "city": city,
        "country": country,
        "channel": channel,
        "is_fraud": is_fraud,
    }


def write_batch(records: list, tag: str) -> Path:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = BATCH_DIR / f"txn_{tag}_{stamp}.batch.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def gen_history(days: int = 90):
    """One-time backfill: spread transactions across the last `days`."""
    now = datetime.now()
    total = 0
    for d in range(days, 0, -1):
        day = now - timedelta(days=d)
        # weekend / weekday volume wobble
        n = int(TXN_PER_BATCH * (0.6 if day.weekday() >= 5 else 1.0))
        records = []
        for _ in range(n):
            ts = day.replace(hour=random.randint(6, 22),
                             minute=random.randint(0, 59),
                             second=random.randint(0, 59))
            records.append(make_txn(ts))
        p = write_batch(records, f"hist{d:03d}")
        total += len(records)
    print(f"History: wrote {total} txns across {days} days into {BATCH_DIR}")


def gen_live(batches: int = 1):
    """Fresh transactions timestamped ~now (for the streaming demo)."""
    for _ in range(batches):
        now = datetime.now()
        records = [make_txn(now - timedelta(seconds=random.randint(0, 300)))
                   for _ in range(TXN_PER_BATCH)]
        p = write_batch(records, "live")
        print(f"Live batch: {len(records)} txns -> {p.name}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "history"
    if mode == "live":
        gen_live(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    else:
        gen_history()
