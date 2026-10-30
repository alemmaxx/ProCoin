"""Robot 5 (ProCoin): maklumat asas coin — nilai pasaran, bekalan, volum 24 jam, paras tertinggi (ATH).

Output: <out>/fund.json dan data/fund.json  {"asof":..., "items": {kod: {...}}}
  mc  nilai pasaran (USD)       rk  kedudukan ikut nilai pasaran dalam senarai ProCoin
  cs  bekalan beredar           ms  bekalan maksimum (None = tiada had)
  v24 volum 24 jam (USD)        ath paras tertinggi 5 tahun & tarikhnya (athd), dath = % di bawah ATH
  y1  perubahan harga 1 tahun (%)
Sumber: Yahoo Finance (yfinance). Angka indikatif.
"""
import argparse
import json
import math
import os
import time
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
STORE = os.path.join(ROOT, "data", "fund.json")


def num(x, nd=0):
    try:
        x = float(x)
        if math.isnan(x) or math.isinf(x) or x <= 0:
            return None
        return round(x, nd) if nd else round(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site", "data"))
    a = ap.parse_args()
    M = json.load(open(os.path.join(a.out, "market.json")))
    coins = {x["code"]: x for x in json.load(open(os.path.join(ROOT, "data", "coins.json")))}
    store = json.load(open(STORE)) if os.path.exists(STORE) else {"items": {}}
    items = {c: v for c, v in store.get("items", {}).items() if c in M["stocks"]}  # buang coin yang sudah dikeluarkan dari senarai
    try:
        import yfinance as yf
    except Exception:
        yf = None
    for c, v in M["stocks"].items():
        f = dict(items.get(c, {}))
        # dari sejarah harga (sentiasa ada)
        try:
            S = json.load(open(os.path.join(a.out, "s", f"{c}.json")))
            hi = S["h"]
            i = max(range(len(hi)), key=lambda k: hi[k] or 0)
            f["ath"], f["athd"] = hi[i], S["d"][i]
            last = S["c"][-1]
            f["dath"] = round((last / hi[i] - 1) * 100, 1) if hi[i] else None
            f["y1"] = round((last / S["c"][-366] - 1) * 100, 1) if len(S["c"]) > 366 and S["c"][-366] else None
        except Exception:
            pass
        if yf and c in coins:
            try:
                info = yf.Ticker(coins[c]["yf"]).info or {}
                for k, src in (("mc", "marketCap"), ("cs", "circulatingSupply"), ("ms", "maxSupply"),
                               ("v24", "volume24Hr")):
                    val = num(info.get(src))
                    if val is not None:
                        f[k] = val
            except Exception as e:
                print("  gagal", c, e)
            time.sleep(0.5)
        f["at"] = M["meta"]["asof"]
        items[c] = {k: x for k, x in f.items() if x is not None}
    ranked = sorted([c for c in items if items[c].get("mc")], key=lambda c: -items[c]["mc"])
    for i, c in enumerate(ranked):
        items[c]["rk"] = i + 1
    out = {"asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "items": items}
    json.dump(out, open(STORE, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(out, open(os.path.join(a.out, "fund.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"✓ Maklumat coin: {len(items)} coin, {len(ranked)} ada nilai pasaran")


if __name__ == "__main__":
    main()
