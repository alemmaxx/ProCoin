"""Semak data harga terkini. Gagalkan job (supaya pemilik dapat emel GitHub) jika data lewat."""
import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")


def main():
    meta = json.load(open(os.path.join(ROOT, "data", "market-meta.json")))
    # Crypto 24/7: bar harian UTC semalam mesti sudah ada
    d = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    asof = meta.get("asof", "")
    if asof < d:
        print(f"::error::Data harga lewat: data terakhir {asof}, sepatutnya {d}. Robot akan cuba semula pada larian seterusnya.")
        raise SystemExit(1)
    print(f"✓ Data harga terkini ({asof})")


if __name__ == "__main__":
    main()
