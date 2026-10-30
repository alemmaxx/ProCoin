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
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from common import analyze  # noqa: E402
import backtest as BT  # noqa: E402
import track  # noqa: E402
import paper  # noqa: E402
import strategies as ST  # noqa: E402
from common import ema as _ema  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
COINS = os.path.join(ROOT, "data", "coins.json")
PROVIDER = "yfinance"
MIN_VALUE = 1_000_000   # nilai dagangan purata 20 hari minimum (USD)
# Strategi yang digunakan untuk isyarat (dibuktikan dalam robot kajian, data/research.json):
#   A = Isyarat aktif (Isyarat Kuat), B = Isyarat Pemerhatian
# Dipilih oleh kajian penerokaan (scripts/explore.py) dengan kos sebenar runcit 1.2% pergi-balik
USE = {"drop2d": "A", "ema2050": "B"}
RULE = {"drop2d": "Masuk bila coin jatuh lebih 15% dalam 2 hari (jualan panik). Keluar bila harga tutup atas EMA10, atau selepas 20 hari. Cut loss 3× ATR.",
        "drop15": "Masuk bila coin jatuh lebih 15% dalam 3 hari tetapi masih atas EMA200. Keluar bila harga tutup atas EMA10, atau selepas 20 hari. Cut loss 3× ATR.",
        "ema2050": "Masuk bila EMA20 lintas atas EMA50 (harga atas EMA200). Pegang selagi trend kekal; keluar bila EMA20 jatuh bawah EMA50."}


def sstats(trs):
    from statistics import median
    n = len(trs)
    if not n:
        return {"n": 0}
    w = [x for x in trs if x["ret"] > 0]
    wd = sorted(x["days"] for x in w)
    q = lambda p: wd[min(len(wd) - 1, int(p * len(wd)))] if wd else None
    return {"n": n, "w": len(w), "p": round(len(w) / n * 100), "md": median(wd) if wd else None, "d25": q(.25), "d75": q(.75),
            "ev": round(sum(x["ret"] for x in trs) / n * 100, 2), "aw": round(sum(x["ret"] for x in w) / len(w) * 100, 2) if w else None,
            "cf": BT.confidence(n)}


def load_coins():
    return json.load(open(COINS))


def prices_yf(coins):
    out = _yf_pass(coins, 25)
    redo = [x for x in coins if x["code"] not in out]
    if out and redo:
        print(f"  cuba semula {len(redo)} coin")
        out.update(_yf_pass(redo, 5))
    # ticker ganti (cth. TON11419-USD → TON-USD) untuk coin yang masih tiada harga
    alt = [{**x, "yf": a} for x in coins if x["code"] not in out for a in x.get("alt", [])[:1]]
    if alt:
        print(f"  cuba ticker ganti untuk {len(alt)} coin: {[a['yf'] for a in alt]}")
        out.update(_yf_pass(alt, 5))
    return out


def fill_from_hourly(coins, px, today_utc):
    """Yahoo kadang-kadang lewat menerbitkan bar harian crypto terkini. Bina bar harian yang tertinggal
    (hari UTC yang sudah lengkap, sebelum hari ini) daripada data sejam. Pulangkan bilangan bar diisi."""
    import yfinance as yf

    filled = 0
    tick = {x["code"]: x["yf"] for x in coins if x["code"] in px}
    try:
        df = yf.download(list(tick.values()), period="5d", interval="1h", group_by="ticker", auto_adjust=True,
                         threads=True, progress=False)
    except Exception as e:
        print("  ! data sejam gagal:", e)
        return 0
    for c, t in tick.items():
        try:
            sub = (df[t] if len(tick) > 1 else df).dropna(subset=["Close"])
        except Exception:
            continue
        if sub.empty:
            continue
        idx = sub.index.tz_convert("UTC") if sub.index.tz is not None else sub.index
        days = {}
        for ix, r in zip(idx, sub.itertuples()):
            days.setdefault(ix.strftime("%Y-%m-%d"), []).append((ix.hour, r))
        last = px[c][-1][0]
        for d in sorted(days):
            if d <= last or d >= today_utc:
                continue
            bars = sorted(days[d], key=lambda z: z[0])
            if len(bars) < 20:   # hari tidak lengkap dalam data sejam — jangan reka bar
                continue
            rs = [b[1] for b in bars]
            px[c].append([d, rs[0].Open, max(b.High for b in rs), min(b.Low for b in rs), rs[-1].Close,
                          sum(0 if math.isnan(b.Volume) else b.Volume for b in rs)])
            last = d
            filled += 1
    return filled


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
    raw_last = px["BTC"][-1][0] if "BTC" in px else None
    try:
        n_fill = fill_from_hourly(coins, px, today_utc)
        if n_fill:
            print(f"  ✓ {n_fill} bar harian yang tertinggal diisi daripada data sejam")
    except Exception as e:
        n_fill = 0
        print("  ! isi bar harian gagal:", e)
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

    # --- strategi crypto (isyarat aktif & pemerhatian)
    btc_rows = px.get("BTC", [])
    btc_cl = [float(r[4]) for r in btc_rows]
    btc_e200 = _ema(btc_cl, 200)
    btc_up = {r[0]: (btc_e200[i] is not None and btc_cl[i] > btc_e200[i]) for i, r in enumerate(btc_rows)}
    SR, pooled = {}, {k: [] for k in USE}
    PERF = []
    PERF_FROM = (datetime.strptime(btc_rows[-1][0], "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d") if btc_rows else "0000"
    for c, rows in px.items():
        if len(rows) < 260:
            continue
        o = [float(r[1] or r[4]) for r in rows]; hh = [float(r[2] or r[4]) for r in rows]
        ll = [float(r[3] or r[4]) for r in rows]; cc = [float(r[4]) for r in rows]; vv = [float(r[5] or 0) for r in rows]
        dates = [r[0] for r in rows]
        SR[c] = {}
        for k in USE:
            trs, _, pos = ST.run_strategy(k, o, hh, ll, cc, vv, btc_ok=lambda t, d=dates: btc_up.get(d[t], False))
            SR[c][k] = (trs, pos)
            pooled[k] += trs
            # prestasi lepas (13 bulan) untuk pop up "Prestasi lepas" di app: pulangan KASAR (app tolak kos platform pengguna)
            for tr in trs:
                if dates[tr["t"]] >= PERF_FROM and tr["t"] + 1 < len(dates):
                    PERF.append([c, k, dates[tr["t"] + 1], dates[min(tr["exit"], len(dates) - 1)], round((tr["ret"] + ST.FEE) * 100, 3), tr["days"], 0])
            if pos and pos["t"] + 1 < len(dates) and dates[pos["t"]] >= PERF_FROM:
                e = o[pos["t"] + 1] or cc[pos["t"]]
                PERF.append([c, k, dates[pos["t"] + 1], dates[-1], round((cc[-1] / e - 1) * 100, 3), len(dates) - 1 - pos["t"], 1])
    PS = {k: sstats(v) for k, v in pooled.items()}
    print("Strategi:", {k: (v["n"], v["p"], v["ev"]) for k, v in PS.items()})

    stocks = {}
    for s in coins:
        c = s["code"]
        rows = px.get(c)
        item = {"n": s["name"], "s": "ok", "k": "coin", **({"cg": s["cg"]} if s.get("cg") else {})}
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
                o_ = [float(r[1] or r[4]) for r in rows]; h_ = [float(r[2] or r[4]) for r in rows]
                L = len(closes) - 1
                e10, e50L = _ema(closes, 10), _ema(closes, 50)
                for k, grade in USE.items():
                    trs, pos = SR.get(c, {}).get(k, ([], None))
                    if not pos:
                        continue
                    t, at = pos["t"], pos["atr"]
                    ago = L - t
                    S = ST.STRATS[k]
                    if ago > S["max"]:
                        continue
                    en = closes[-1] if ago == 0 else (o_[t + 1] or closes[t])
                    stop = en - S["k"] * at if S.get("k") else 0.0   # ema2050: tiada stop ATR, keluar ikut trend
                    st = PS[k]
                    if k in ("drop15", "drop2d"):
                        tg = max(e10[L] or en * 1.01, en * 1.005)
                    else:
                        tg = en * (1 + (st.get("aw") or 5) / 100)
                    ops.append({"k": k, "st": k, "g": grade, "p": st["p"], "n": st["n"], "w": st["w"], "cf": st["cf"],
                                "md": st["md"], "d25": st["d25"], "d75": st["d75"], "ev": st["ev"], "ago": ago,
                                "en": r3(en), "tg": r3(tg), "sl": r3(stop), "atr": r3(at), "rule": RULE[k]})
                if ops and liq:
                    ops.sort(key=lambda x: (x["g"], x["ago"]))
                    item["op"] = ops
                bt = {k: sstats(SR.get(c, {}).get(k, ([], None))[0]) for k in USE}
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
        "asof": asof, "provider": PROVIDER, "currency": "USD", "rawLast": raw_last, "hourFill": n_fill,
        "count": len(stocks), "priced": len(px),
        "bt": {"h": BT.H, "tgt": BT.TGT_ATR, "stp": BT.STP_ATR, "fee": BT.FEE},
        "setups": {**{k: {"name": BT.SETUPS[k], "n": g["n"], "p": round(prior[k] * 100), "md": g["md"],
                          "d25": g["d25"], "d75": g["d75"], "ev": g["ev"]} for k, g in gstats.items()},
                   **{k: {"name": ST.STRATS[k]["name"], **PS[k], "grade": USE[k], "rule": RULE[k], "kATR": ST.STRATS[k].get("k"),
                          "max": ST.STRATS[k]["max"]} for k in USE}},
        "strat": {k: USE[k] for k in USE},
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
    PERF.sort(key=lambda x: (x[2], x[0]))
    BTCC = [[r[0], r3(float(r[4]))] for r in btc_rows if r[0] >= PERF_FROM]
    json.dump({"asof": asof, "from": PERF_FROM, "cols": ["c", "k", "in", "out", "gross%", "days", "open"], "fee_bt": ST.FEE,
               "use": USE, "t": PERF, "btc": BTCC}, open(os.path.join(a.out, "perf.json"), "w"), separators=(",", ":"))
    print(f"✓ perf.json: {len(PERF)} dagangan sejak {PERF_FROM}")
    json.dump({"meta": meta, "stocks": stocks}, open(os.path.join(a.out, "market.json"), "w"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"✓ market.json: {len(stocks)} coin, {len(px)} berharga, data setakat {asof}")


if __name__ == "__main__":
    main()
