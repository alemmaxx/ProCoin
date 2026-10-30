"""Robot kajian: backtest penapis untuk Isyarat aktif (dijalankan di GitHub, data sebenar).

Untuk setiap isyarat dalam sejarah ~5 tahun (4 persediaan beli, enjin backtest.py), robot merekod hasil
(MENANG / KALAH / TAMAT, pulangan selepas kos) dan ciri pada hari isyarat:
  btc     keadaan Bitcoin: naik / datar / turun (harga vs purata 50 & 200 hari)
  rs30    kekuatan relatif: pulangan 30 hari coin − pulangan 30 hari BTC (%)
  fng     Fear & Greed Index (alternative.me) pada hari itu
  h4      trend carta 4 jam pada penutup harian (EMA20 > EMA50 dan MACD > garis isyarat) — 2 tahun terakhir sahaja
  p_wf    kebarangkalian WALK-FORWARD: hanya guna dagangan coin+persediaan yang SUDAH selesai sebelum hari isyarat
  ev_wf   purata pulangan walk-forward (%)
Gred "Isyarat Kuat" disimulasi seperti app (kelebihan ≥ 10 mata atas paras neutral, ≥ 8 contoh, purata pulangan > 0)
tetapi guna statistik walk-forward, supaya tiada maklumat masa depan.

Keputusan: data/research.json — perbandingan setiap penapis, ranking ikut jangkaan untung (EV),
model logistik gabungan (latih 60% awal, uji 40% akhir), dan kalibrasi.
"""
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
import backtest as BT  # noqa: E402
from common import ema, ema_sparse, rsi  # noqa: E402
import market  # noqa: E402
import strategies as ST  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "data", "research.json")
PRIOR_K = BT.PRIOR_K


# ---------------- data ----------------
def fear_greed():
    """{YYYY-MM-DD: nilai 0-100}. Kosong jika gagal."""
    try:
        r = requests.get("https://api.alternative.me/fng/", params={"limit": 0, "format": "json"}, timeout=30)
        r.raise_for_status()
        return {datetime.fromtimestamp(int(x["timestamp"]), timezone.utc).strftime("%Y-%m-%d"): int(x["value"])
                for x in r.json().get("data", [])}
    except Exception as e:
        print("! Fear & Greed gagal:", e)
        return {}


def hourly(coins):
    """{kod: [(datetime UTC, close)]} untuk ~2 tahun (had Yahoo: 730 hari untuk data sejam)."""
    import yfinance as yf
    out = {}
    tick = {x["code"]: x["yf"] for x in coins}
    for i in range(0, len(coins), 10):
        chunk = coins[i:i + 10]
        try:
            df = yf.download([x["yf"] for x in chunk], period="730d", interval="1h", group_by="ticker",
                             auto_adjust=True, threads=True, progress=False)
        except Exception as e:
            print("  ! data sejam gagal:", e)
            continue
        for x in chunk:
            try:
                sub = (df[x["yf"]] if len(chunk) > 1 else df).dropna(subset=["Close"])
            except Exception:
                continue
            idx = sub.index.tz_convert("UTC") if sub.index.tz is not None else sub.index
            out[x["code"]] = [(ix.to_pydatetime(), float(c)) for ix, c in zip(idx, sub["Close"])]
        time.sleep(2)
    print(f"  data sejam: {len(out)} coin")
    return out


def h4_trend(hrs):
    """{YYYY-MM-DD: True/False} — trend 4 jam pada penutup hari UTC itu (bar 4 jam terakhir hari tersebut)."""
    bars = {}
    for t, c in hrs:
        key = (t.strftime("%Y-%m-%d"), t.hour // 4)
        bars[key] = c  # harga tutup terakhir dalam blok 4 jam
    keys = sorted(bars)
    cl = [bars[k] for k in keys]
    if len(cl) < 80:
        return {}
    e20, e50 = ema(cl, 20), ema(cl, 50)
    e12, e26 = ema(cl, 12), ema(cl, 26)
    mac = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
    sig = ema_sparse(mac, 9)
    out = {}
    for i, k in enumerate(keys):
        if None in (e20[i], e50[i], mac[i], sig[i]):
            continue
        out[k[0]] = bool(e20[i] > e50[i] and mac[i] > sig[i])  # blok terakhir hari menang (susunan menaik)
    return out


def btc_regime(rows):
    cl = [float(r[4]) for r in rows]
    out = {}
    for i in range(200, len(rows)):
        c, m50, m200 = cl[i], sum(cl[i - 49:i + 1]) / 50, sum(cl[i - 199:i + 1]) / 200
        out[rows[i][0]] = "naik" if c > m50 > m200 else ("turun" if c < m50 < m200 else "datar")
    return out


# ---------------- statistik ----------------
def summ(ev):
    n = len(ev)
    if not n:
        return {"n": 0}
    rets = [e["ret"] for e in ev]
    w = sum(1 for e in ev if e["res"] == "W")
    pos, neg = sum(r for r in rets if r > 0), -sum(r for r in rets if r < 0)
    avg = sum(rets) / n
    sd = math.sqrt(sum((r - avg) ** 2 for r in rets) / (n - 1)) if n > 1 else 0
    return {"n": n, "win": round(w / n * 100, 1), "avg": round(avg, 2), "tot": round(sum(rets), 1),
            "pf": round(pos / neg, 2) if neg else None, "ci": round(1.96 * sd / math.sqrt(n), 2) if n > 1 else None}


def auc(y, p):
    pos = [pp for yy, pp in zip(y, p) if yy]
    neg = [pp for yy, pp in zip(y, p) if not yy]
    if not pos or not neg:
        return None
    allp = sorted((pp, yy) for yy, pp in zip(y, p))
    rank, i = {}, 0
    ranks = [0.0] * len(allp)
    while i < len(allp):
        j = i
        while j + 1 < len(allp) and allp[j + 1][0] == allp[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    rp = sum(r for r, (pp, yy) in zip(ranks, allp) if yy)
    return round((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)), 3)


FEATS = ["p_wf", "edge", "ev_wf", "sc", "rsi", "btc_naik", "btc_turun", "rs30", "fng", "h4_up", "h4_na",
         "k_pb", "k_gc", "k_mc", "k_os"]


def fvec(e):
    h4 = e.get("h4")
    return [e["p_wf"], e["edge"], max(-20, min(20, e["ev_wf"] or 0)) / 10, e["sc"] / 5, (e["rsi"] or 50) / 100,
            1.0 if e["btc"] == "naik" else 0.0, 1.0 if e["btc"] == "turun" else 0.0,
            max(-100, min(100, e["rs30"] or 0)) / 100, (e["fng"] if e["fng"] is not None else 50) / 100,
            1.0 if h4 is True else 0.0, 1.0 if h4 is None else 0.0,
            *[1.0 if e["k"] == k else 0.0 for k in ("pb", "gc", "mc", "os")]]


def logit_fit(X, y, l2=0.5, it=600, lr=0.5):
    import numpy as np
    X = np.array(X, float)
    y = np.array(y, float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]] / len(y)
        w -= lr * g
    return {"w": w.tolist(), "mu": mu.tolist(), "sd": sd.tolist()}


def logit_pred(m, X):
    import numpy as np
    X = np.array(X, float)
    Z = np.c_[np.ones(len(X)), (X - np.array(m["mu"])) / np.array(m["sd"])]
    return (1 / (1 + np.exp(-Z @ np.array(m["w"])))).tolist()


# ---------------- utama ----------------
def main():
    coins = market.load_coins()
    print(f"Kajian: tarik harga harian {len(coins)} coin …")
    px = market.prices_yf(coins)
    today_utc = datetime.now(timezone.utc).date().isoformat()
    px = {c: [r for r in rows if r[0] < today_utc] for c, rows in px.items() if len(rows) > 260}
    if "BTC" not in px:
        raise SystemExit("GAGAL: tiada data BTC")
    fng = fear_greed()
    H = hourly(coins)
    H4 = {c: h4_trend(v) for c, v in H.items()}
    reg = btc_regime(px["BTC"])
    btc_c = {r[0]: float(r[4]) for r in px["BTC"]}
    btc_d = [r[0] for r in px["BTC"]]

    # --- semua isyarat dalam sejarah
    events = []
    for code, rows in px.items():
        o = [float(r[1] or r[4]) for r in rows]; h = [float(r[2] or r[4]) for r in rows]
        l = [float(r[3] or r[4]) for r in rows]; c = [float(r[4]) for r in rows]; v = [float(r[5] or 0) for r in rows]
        dates = [r[0] for r in rows]
        R = BT.run(o, h, l, c, v)
        rs = rsi(c, 14)
        for k, trs in R["trades"].items():
            for tr in trs:
                t = tr["t"]
                d = dates[t]
                ex = dates[min(len(dates) - 1, t + tr["days"])]
                rs30 = None
                if t >= 30 and d in btc_c:
                    i = btc_d.index(d)
                    if i >= 30:
                        rs30 = (c[t] / c[t - 30] - 1) * 100 - (btc_c[d] / btc_c[btc_d[i - 30]] - 1) * 100
                events.append({"code": code, "k": k, "d": d, "x": ex, "res": tr["res"], "ret": tr["ret"] * 100,
                               "tp": tr["tp"], "sp": tr["sp"], "sc": tr.get("sc", 0), "rsi": rs[t],
                               "btc": reg.get(d), "rs30": rs30, "fng": fng.get(d),
                               "h4": H4.get(code, {}).get(d)})
    events.sort(key=lambda e: e["d"])
    print(f"  {len(events)} isyarat dalam sejarah")

    # --- statistik walk-forward (hanya dagangan yang sudah selesai sebelum hari isyarat)
    for e in events:
        prev = [x for x in events if x["k"] == e["k"] and x["x"] < e["d"]]
        mine = [x for x in prev if x["code"] == e["code"]]
        gp = sum(1 for x in prev if x["res"] == "W") / len(prev) if prev else 0.35
        n, w = len(mine), sum(1 for x in mine if x["res"] == "W")
        e["n_wf"] = n
        e["p_wf"] = (w + PRIOR_K * gp) / (n + PRIOR_K)
        e["ev_wf"] = sum(x["ret"] for x in mine) / n if n else None
        be = (e["sp"] + BT.FEE) / (e["tp"] + e["sp"])
        e["edge"] = e["p_wf"] - be
        e["A"] = e["edge"] >= 0.10 and n >= 8 and (e["ev_wf"] or 0) > 0
        e["B"] = (not e["A"]) and e["edge"] >= 0.05 and n >= 5 and (e["ev_wf"] or 0) > 0
    # buang tahun pertama (statistik walk-forward belum cukup)
    start = (date.fromisoformat(events[0]["d"]) + timedelta(days=365)).isoformat()
    ev = [e for e in events if e["d"] >= start]
    A = [e for e in ev if e["A"]]
    AB = [e for e in ev if e["A"] or e["B"]]
    print(f"  diuji: {len(ev)} isyarat sejak {start}; Isyarat Kuat {len(A)}, Kuat+Sederhana {len(AB)}")

    F = [
        ("semua", "Tanpa penapis", lambda e: True),
        ("btc_ok", "BTC tidak menurun", lambda e: e["btc"] in ("naik", "datar")),
        ("btc_up", "BTC menaik", lambda e: e["btc"] == "naik"),
        ("rs_pos", "Lebih kuat daripada BTC (30 hari)", lambda e: (e["rs30"] or 0) > 0),
        ("fng_lt75", "Fear & Greed bawah 75 (bukan tamak melampau)", lambda e: e["fng"] is not None and e["fng"] < 75),
        ("fng_le50", "Fear & Greed 50 ke bawah (pasaran takut)", lambda e: e["fng"] is not None and e["fng"] <= 50),
        ("btc_rs", "BTC tidak menurun + lebih kuat daripada BTC", lambda e: e["btc"] in ("naik", "datar") and (e["rs30"] or 0) > 0),
    ]
    def block(group, name):
        rows = []
        base = summ(group)
        for key, label, f in F:
            s = summ([e for e in group if f(e)])
            rows.append({"key": key, "name": label, **s})
        # trend 4 jam: dibanding atas tempoh yang sama (data sejam hanya ~2 tahun)
        sub = [e for e in group if e["h4"] is not None]
        if sub:
            rows.append({"key": "h4_base", "name": "Tempoh 2 tahun (data 4 jam ada) — tanpa penapis", **summ(sub)})
            rows.append({"key": "h4_up", "name": "Trend 4 jam menaik", **summ([e for e in sub if e["h4"]])})
            rows.append({"key": "h4_btc", "name": "Trend 4 jam menaik + BTC tidak menurun",
                         **summ([e for e in sub if e["h4"] and e["btc"] in ("naik", "datar")])})
            rows.append({"key": "h4_all", "name": "4 jam menaik + BTC tidak menurun + lebih kuat daripada BTC",
                         **summ([e for e in sub if e["h4"] and e["btc"] in ("naik", "datar") and (e["rs30"] or 0) > 0])})
        return {"name": name, "base": base, "rows": rows}

    groups = [block(A, "Isyarat Kuat"), block(AB, "Isyarat Kuat + Sederhana"), block(ev, "Semua isyarat (tanpa gred)")]

    # --- ranking ikut jangkaan untung (EV walk-forward) berbanding ikut % menang
    def halves(group, key):
        g = sorted([e for e in group if e[key] is not None], key=lambda e: e[key])
        m = len(g) // 2
        return {"low": summ(g[:m]), "high": summ(g[m:])}
    rank = {"ev": halves(AB, "ev_wf"), "p": halves(AB, "p_wf")}

    # --- model logistik gabungan: latih 60% awal, uji 40% akhir (walk-forward)
    model = None
    try:
        cut = ev[int(len(ev) * 0.6)]["d"]
        tr = [e for e in ev if e["x"] < cut]
        te = [e for e in ev if e["d"] >= cut]
        m = logit_fit([fvec(e) for e in tr], [1 if e["ret"] > 0 else 0 for e in tr])
        pt = logit_pred(m, [fvec(e) for e in te])
        for e, p in zip(te, pt):
            e["pm"] = p
        y = [1 if e["ret"] > 0 else 0 for e in te]
        calib = []
        for lo, hi in [(0, .4), (.4, .5), (.5, .6), (.6, 1.01)]:
            xs = [e for e in te if lo <= e["pm"] < hi]
            if xs:
                calib.append({"band": f"{int(lo*100)}-{min(100,int(hi*100))}", "n": len(xs),
                              "pred": round(sum(e["pm"] for e in xs) / len(xs) * 100),
                              "act": round(sum(1 for e in xs if e["ret"] > 0) / len(xs) * 100)})
        top = sorted(te, key=lambda e: -e["pm"])[:max(1, len(te) // 5)]
        thr = sorted(e["pm"] for e in te)[int(len(te) * 0.8)] if te else 0.5
        full = logit_fit([fvec(e) for e in ev], [1 if e["ret"] > 0 else 0 for e in ev])
        model = {"train_to": cut, "n_train": len(tr), "n_test": len(te), "auc": auc(y, pt),
                 "auc_pwf": auc(y, [e["p_wf"] for e in te]), "calib": calib,
                 "test_all": summ(te), "test_A": summ([e for e in te if e["A"]]), "test_top20": summ(top),
                 "test_A_top": summ([e for e in te if e["A"] and e["pm"] >= thr]),
                 "thr": round(thr, 3), "feats": FEATS, "coef": [round(x, 3) for x in full["w"]],
                 "live": full}
        print(f"  model: AUC {model['auc']} (p walk-forward sahaja {model['auc_pwf']}), top20 {model['test_top20']}")
    except Exception as e:
        print("! model gagal:", e)

    # --- kalibrasi % peluang: kebarangkalian sejarah (walk-forward) vs kadar menang sebenar
    calib_p = []
    for lo, hi in [(0, .35), (.35, .45), (.45, .55), (.55, .65), (.65, 1.01)]:
        xs = [e for e in ev if lo <= e["p_wf"] < hi]
        if xs:
            calib_p.append({"lo": round(lo * 100), "hi": min(100, round(hi * 100)), "n": len(xs),
                            "pred": round(sum(e["p_wf"] for e in xs) / len(xs) * 100),
                            "act": round(sum(1 for e in xs if e["res"] == "W") / len(xs) * 100),
                            "avg": round(sum(e["ret"] for e in xs) / len(xs), 2)})

    # --- strategi crypto baharu (peraturan tetap, tiada parameter dilatih)
    btc_rows = px["BTC"]
    btc_cl = [float(r[4]) for r in btc_rows]
    btc_e200 = ema(btc_cl, 200)
    btc_up = {r[0]: (btc_e200[i] is not None and btc_cl[i] > btc_e200[i]) for i, r in enumerate(btc_rows)}
    mid = None
    strat = []
    for key, S in ST.STRATS.items():
        alltr = []
        for code, rows in px.items():
            o = [float(r[1] or r[4]) for r in rows]; h = [float(r[2] or r[4]) for r in rows]
            l = [float(r[3] or r[4]) for r in rows]; c = [float(r[4]) for r in rows]; v = [float(r[5] or 0) for r in rows]
            dates = [r[0] for r in rows]
            trs, _, _ = ST.run_strategy(key, o, h, l, c, v, btc_ok=lambda t, d=dates: btc_up.get(d[t], False))
            for tr in trs:
                d = dates[tr["t"]]
                if d >= start:
                    alltr.append({"d": d, "ret": tr["ret"] * 100, "days": tr["days"], "res": "W" if tr["ret"] > 0 else "L"})
        alltr.sort(key=lambda x: x["d"])
        if not alltr:
            continue
        if mid is None:
            mid = (date.fromisoformat(start) + (date.fromisoformat(ev[-1]["d"]) - date.fromisoformat(start)) / 2).isoformat()
        s_all, s1, s2 = summ(alltr), summ([x for x in alltr if x["d"] < mid]), summ([x for x in alltr if x["d"] >= mid])
        years = {}
        for x in alltr:
            years.setdefault(x["d"][:4], []).append(x)
        ys = {y: summ(v) for y, v in sorted(years.items())}
        pos_years = sum(1 for y in ys.values() if (y.get("avg") or 0) > 0)
        proven = bool(s_all["n"] >= 50 and (s_all.get("pf") or 0) >= 1.15 and (s1.get("avg") or 0) > 0 and (s2.get("avg") or 0) > 0
                      and pos_years >= max(2, round(len(ys) * 0.6)))
        strat.append({"key": key, "name": S["name"], "all": s_all, "h1": s1, "h2": s2, "years": ys, "proven": proven,
                      "days": round(sum(x["days"] for x in alltr) / len(alltr), 1)})
        print(f"  strategi {key}: {s_all} | separuh 1 {s1.get('avg')} | separuh 2 {s2.get('avg')} | terbukti {proven}")
    base_tr = [{"d": e["d"], "ret": e["ret"], "res": e["res"], "days": 0} for e in ev]
    strat.insert(0, {"key": "base", "name": "Isyarat asal (4 corak, sasaran 2× ATR, cut loss 1.25× ATR)", "all": summ(base_tr),
                     "h1": summ([x for x in base_tr if mid and x["d"] < mid]), "h2": summ([x for x in base_tr if mid and x["d"] >= mid]),
                     "years": {}, "proven": False, "days": None})
    bh = {}
    for code in ("BTC", "ETH"):
        rows = [r for r in px.get(code, []) if r[0] >= start]
        if rows:
            bh[code] = round((float(rows[-1][4]) / float(rows[0][4]) - 1) * 100, 1)

    out = {"asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "start": start, "mid": mid,
           "calib_p": calib_p, "strat": strat, "hold": bh, "end": ev[-1]["d"] if ev else None,
           "fee": BT.FEE, "h": BT.H, "tgt": BT.TGT_ATR, "stp": BT.STP_ATR, "coins": len(px), "n": len(ev),
           "fng_ok": bool(fng), "h4_coins": len([c for c in H4 if H4[c]]),
           "groups": groups, "rank": rank, "model": model}
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    for g in groups:
        print("==", g["name"])
        for r in g["rows"]:
            print(f"   {r['name']}: n={r.get('n')} menang={r.get('win')}% purata={r.get('avg')}% ±{r.get('ci')} pf={r.get('pf')}")
    print("✓ data/research.json")


if __name__ == "__main__":
    main()
