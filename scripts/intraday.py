"""Robot 4 (ProCoin): harga 30 minit (sebulan lepas) untuk semua coin — untuk carta 30m / 1 jam dalam app.

Output: <out>/i/<kod>.json  {"t":[...], "o":[...], "h":[...], "l":[...], "c":[...], "v":[...]}
Masa dalam waktu Malaysia (YYYY-MM-DD HH:MM). Bukan masa nyata: dikemas kini setiap kali robot berjalan.
"""
import argparse
import json
import math
import os
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
MAX_STOCKS = 60


def r4(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    x = float(x)
    return 0.0 if x == 0 else round(x, min(12, max(2, 5 - int(math.floor(math.log10(abs(x)))))))


def main():
    import yfinance as yf

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site", "data"))
    a = ap.parse_args()
    M = json.load(open(os.path.join(a.out, "market.json")))
    stocks = M["stocks"]
    yfmap = {x["code"]: x["yf"] for x in json.load(open(os.path.join(ROOT, "data", "coins.json")))}
    codes = [c for c, v in stocks.items() if v.get("c") and c in yfmap][:MAX_STOCKS]
    os.makedirs(os.path.join(a.out, "i"), exist_ok=True)
    done = []
    for i in range(0, len(codes), 40):
        chunk = codes[i:i + 40]
        tick = [yfmap[c] for c in chunk]
        try:
            df = yf.download(tick, period="1mo", interval="30m", group_by="ticker", auto_adjust=True, threads=True, progress=False)
        except Exception as e:
            print("  gagal", e)
            continue
        for c, t in zip(chunk, tick):
            try:
                sub = (df[t] if len(tick) > 1 else df).dropna(subset=["Close"])
            except Exception:
                continue
            if len(sub) < 10:
                continue
            idx = sub.index.tz_convert("Asia/Kuala_Lumpur") if sub.index.tz is not None else sub.index
            out = {"t": [x.strftime("%Y-%m-%d %H:%M") for x in idx],
                   "o": [r4(x) for x in sub["Open"]], "h": [r4(x) for x in sub["High"]],
                   "l": [r4(x) for x in sub["Low"]], "c": [r4(x) for x in sub["Close"]],
                   "v": [0 if (x is None or (isinstance(x, float) and math.isnan(x))) else int(x) for x in sub["Volume"]]}
            json.dump(out, open(os.path.join(a.out, "i", f"{c}.json"), "w"), separators=(",", ":"))
            done.append(c)
        time.sleep(2)
    json.dump({"codes": done}, open(os.path.join(a.out, "i", "index.json"), "w"), separators=(",", ":"))
    print(f"✓ Harga 30 minit: {len(done)} coin")


if __name__ == "__main__":
    main()
