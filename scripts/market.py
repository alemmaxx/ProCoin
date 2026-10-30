"""Robot 2 (ProCoin): tarik harga harian coin crypto besar, kira indicator, tulis fail data untuk app.

Senarai coin: data/coins.json (boleh diubah: code, name, yf = ticker Yahoo, q = kata carian berita).
Output (dalam folder --out, cth. _site/data):
  market.json      ringkasan semua coin: harga (USD), sparkline, skor, RSI, peluang ...
  s/<kod>.json     sejarah harga ~5 tahun setiap coin (dibuka bila pengguna lihat carta)
  klci.json        siri Bitcoin (BTC) — digunakan app sebagai "rejim pasaran" crypto
Penyedia harga: yfinance (percuma). Crypto berdagang 24/7; satu "hari" = hari kalendar UTC.
"""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from common import analyze  # noqa: E402
import backtest as BT  # noqa: E402
import track  # noqa: E402
import paper  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
COINS = os.path.join(ROOT, "data", "coins.json")
PROVIDER = "yfinance"
MIN_VALUE = 1_000_000   # nilai dagangan purata 20 hari minimum (USD)


def load_coins():
    return json.load(open(COINS))


def prices_yf(coins):
    out = _yf_pass(coins, 25)
    redo = [x for x in coins if x["code"] not in out]
    if out and redo:
        print(f"  cuba semula {len(redo)} coin")
        out.update(_yf_pass(redo, 5))
    return out


def _yf_pass(coins, size):
    import yfinance as yf

    out = {}
    for i in range(0, len(coins), size):
        chunk = coins[i : i + size]
        tick = [x["yf"] for x in chunk]
        df = None
        for attempt in range(3):
            try:
                df = yf.download(tick, period="5y", interval="1d", group_by="ticker", auto_adjust=True,
                                 threads=True, progress=False)
                break
            except Exception as e:  # rangkaian / had kadar
                print("  cuba semula:", e)
                time.sleep(10)
        if df is None:
            continue
        for x, t in zip(chunk, tick):
            try:
                sub = df[t] if len(tick) > 1 else df
                sub = sub.dropna(subset=["Close"])
            except Exception:
                continue
            if len(sub) < 5:
                continue
            out[x["code"]] = [
                [ix.strftime("%Y-%m-%d"), r.Open, r.High, r.Low, r.Close, 0 if math.isnan(r.Volume) else r.Volume]
                for ix, r in sub.iterrows()
            ]
        print(f"  harga {min(i + size, len(coins))}/{len(coins)}")
        time.sleep(2)
    return out


def r3(x):
    """Bundar ikut magnitud supaya coin murah (cth. SHIB 0.0000123) kekal tepat."""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    x = float(x)
    if x == 0:
        return 0.0
    d = max(2, 5 - int(math.floor(math.log10(abs(x)))))
    return round(x, min(d, 12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site", "data"))
    ap.add_argument("--limit", type=int, default=0, help="untuk ujian: had bilangan coin")
    a = ap.parse_args()

    coins = load_coins()
    if a.limit:
        coins = coins[: a.limit]
    print(f"Tarik harga {len(coins)} coin guna yfinance …")
    px = prices_yf(coins)
    # Buang bar hari ini (UTC) — belum lengkap kerana crypto masih berdagang
    today_utc = datetime.now(timezone.utc).date().isoformat()
    px = {c: [r for r in rows if r[0] < today_utc] for c, rows in px.items()}
    px = {c: rows for c, rows in px.items() if len(rows) >= 5}
    if len(px) < max(3, len(coins) * 0.5):
        raise SystemExit(f"GAGAL: hanya {len(px)} coin ada harga. Data lama tidak diganti.")

    os.makedirs(os.path.join(a.out, "s"), exist_ok=True)

    # --- Backtest semua coin (laluan 1), kumpul statistik pasaran sebagai "prior" ---
    print("Backtest persediaan beli …")
    runs, glob = {}, {k: [] for k in BT.SETUPS}
    for c, rows in px.items():
        o = [float(r[1] or r[4]) for r in rows]; hh = [float(r[2] or r[4]) for r in rows]
        ll = [float(r[3] or r[4]) for r in rows]; cc = [float(r[4]) for r in rows]; vv = [float(r[5] or 0) for r in rows]
        if len(cc) < 260:
            continue
        R = BT.run(o, hh, ll, cc, vv)
        runs[c] = R
        for k, tr in R["trades"].items():
            glob[k] += tr
    gstats = {k: BT.stats(tr) for k, tr in glob.items()}
    prior = {k: (st["w"] / st["n"] if st["n"] else 0.35) for k, st in gstats.items()}

    stocks = {}
    for s in coins:
        c = s["code"]
        rows = px.get(c)
        item = {"n": s["name"], "s": "ok", "k": "coin"}
        bt = None
        if rows:
            closes = [float(r[4]) for r in rows]
            vols = [float(r[5] or 0) for r in rows]
            A = analyze(closes, vols)
            vals = [float(r[5] or 0) for r in rows[-20:]]  # volum crypto Yahoo sudah dalam USD
            avg_val = sum(vals) / len(vals) if vals else 0
            liq = avg_val >= MIN_VALUE
            item["liq"] = 1 if liq else 0
            item["tv"] = round(avg_val)
            item.update({
                "d": rows[-1][0], "c": r3(closes[-1]),
                "ch": r3((closes[-1] / closes[-2] - 1) * 100) if len(closes) > 1 and closes[-2] else None,
                "sp": [r3(x) for x in closes[-40:]],
                **(A or {}),
            })
            R = runs.get(c)
            if R:
                bt = {}
                for k, tr in R["trades"].items():
                    stt = BT.stats(tr)
                    stt["p"] = round(BT.prob(stt, prior[k]) * 100)
                    stt["cf"] = BT.confidence(stt["n"])
                    bt[k] = stt
                ops = []
                for act in R["active"]:
                    k = act["k"]; stt = bt[k]
                    if k in BT.DISABLED:
                        continue
                    last = closes[-1]
                    ops.append({
                        "k": k, "p": stt["p"], "n": stt["n"], "w": stt["w"], "cf": stt["cf"],
                        "md": stt["md"] if stt["md"] is not None else gstats[k]["md"],
                        "d25": stt["d25"] if stt["d25"] is not None else gstats[k]["d25"],
                        "d75": stt["d75"] if stt["d75"] is not None else gstats[k]["d75"],
                        "ev": stt["ev"], "ago": act["t"],
                        "en": r3(last), "tg": r3(last * (1 + act["tp"])), "sl": r3(last * (1 - act["sp"])),
                    })
                if ops and liq:
                    ops.sort(key=lambda x: -x["p"])
                    item["op"] = ops
            keep = rows[-1830:]  # ~5 tahun: untuk carta bulanan & tahunan
            out = {"d": [r[0] for r in keep], "o": [r3(r[1]) for r in keep], "h": [r3(r[2]) for r in keep],
                   "l": [r3(r[3]) for r in keep], "c": [r3(r[4]) for r in keep], "v": [int(r[5] or 0) for r in keep]}
            if bt:
                out["bt"] = bt
                out["atr"] = r3(R["atr"])
            json.dump(out, open(os.path.join(a.out, "s", f"{c}.json"), "w"), separators=(",", ":"))
        stocks[c] = item
    asof = max((v.get("d", "") for v in stocks.values()), default="")
    track.update(px, stocks, asof, a.out)
    paper.build(runs, px, stocks, asof, a.out)
    try:
        import exits
        if exits.due():
            exits.run(px, {c for c, v in stocks.items() if v.get("s") == "ok"}, asof)
    except Exception as e:
        print("! Eksperimen cara keluar gagal:", e)
    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "asof": asof, "provider": PROVIDER, "currency": "USD",
        "count": len(stocks), "priced": len(px),
        "bt": {"h": BT.H, "tgt": BT.TGT_ATR, "stp": BT.STP_ATR, "fee": BT.FEE},
        "setups": {k: {"name": BT.SETUPS[k], "n": g["n"], "p": round(prior[k] * 100), "md": g["md"],
                       "d25": g["d25"], "d75": g["d75"], "ev": g["ev"]} for k, g in gstats.items()},
    }
    K = [[r[0], r3(r[4])] for r in px.get("BTC", [])]
    if len(K) > 60:
        cl = [x[1] for x in K]
        ma50 = sum(cl[-50:]) / 50
        ma200 = sum(cl[-200:]) / min(200, len(cl))
        meta["klci"] = {"d": K[-1][0], "c": cl[-1], "ch": round((cl[-1] / cl[-2] - 1) * 100, 2),
                        "m1": round((cl[-1] / cl[-31] - 1) * 100, 2) if len(cl) > 31 else None,
                        "up": 1 if cl[-1] > ma50 > ma200 else (-1 if cl[-1] < ma50 < ma200 else 0)}
        json.dump({"asof": K[-1][0], "bars": K}, open(os.path.join(a.out, "klci.json"), "w"), separators=(",", ":"))
        json.dump({"asof": K[-1][0], "bars": K}, open(os.path.join(ROOT, "data", "klci.json"), "w"), separators=(",", ":"))
        try:
            import regime
            if regime.due():
                regime.run(runs, px, {c for c, v in stocks.items() if v.get("s") == "ok"}, K, asof)
        except Exception as e:
            print("! Eksperimen rejim pasaran gagal:", e)
    json.dump({"meta": meta, "stocks": stocks}, open(os.path.join(a.out, "market.json"), "w"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"✓ market.json: {len(stocks)} coin, {len(px)} berharga, data setakat {asof}")


if __name__ == "__main__":
    main()
