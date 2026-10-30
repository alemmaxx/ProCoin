"""Robot 6 (ProCoin): ciri tambahan untuk Isyarat aktif — dikira setiap hari selepas market.py & intraday.py.

Output: <out>/features.json dan data/features.json
  fng     Fear & Greed Index terkini (alternative.me)
  btc     keadaan Bitcoin (naik / datar / turun)
  coins   {kod: {rs30, h4, fund, oi, pm}}
    rs30  pulangan 30 hari coin − BTC (%)
    h4    trend carta 4 jam (EMA20 > EMA50 dan MACD > isyarat), dari data 30 minit
    fund  funding rate perpetual terkini (%), oi = open interest (USD) — OKX, jika ada
    pm    {persediaan: kebarangkalian model gabungan (%)} untuk isyarat aktif, guna model dari data/research.json
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from common import ema, ema_sparse  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", params={"limit": 1, "format": "json"}, timeout=20)
        x = r.json()["data"][0]
        return {"v": int(x["value"]), "lbl": x.get("value_classification", "")}
    except Exception as e:
        print("! Fear & Greed gagal:", e)
        return None


def okx(code):
    """Funding rate (%) & open interest (USD) perpetual USDT di OKX. None jika tiada / gagal."""
    inst = f"{code}-USDT-SWAP"
    out = {}
    try:
        r = requests.get("https://www.okx.com/api/v5/public/funding-rate", params={"instId": inst}, timeout=15)
        d = r.json().get("data") or []
        if d:
            out["fund"] = round(float(d[0]["fundingRate"]) * 100, 4)
    except Exception:
        pass
    try:
        r = requests.get("https://www.okx.com/api/v5/public/open-interest", params={"instType": "SWAP", "instId": inst}, timeout=15)
        d = r.json().get("data") or []
        if d and d[0].get("oiUsd"):
            out["oi"] = round(float(d[0]["oiUsd"]))
    except Exception:
        pass
    return out


def h4_from_intra(path):
    """Trend 4 jam terkini daripada bar 30 minit (masa dalam MYT → blok 4 jam UTC)."""
    from datetime import timedelta
    try:
        J = json.load(open(path))
    except Exception:
        return None
    blocks = {}
    for t, c in zip(J["t"], J["c"]):
        if c is None:
            continue
        u = datetime.strptime(t, "%Y-%m-%d %H:%M") - timedelta(hours=8)
        blocks[(u.strftime("%Y-%m-%d"), u.hour // 4)] = c  # harga tutup terakhir setiap blok
    cl = [blocks[k] for k in sorted(blocks)]
    if len(cl) < 80:
        return None
    e20, e50 = ema(cl, 20), ema(cl, 50)
    e12, e26 = ema(cl, 12), ema(cl, 26)
    mac = [x - y if x is not None and y is not None else None for x, y in zip(e12, e26)]
    sig = ema_sparse(mac, 9)
    if None in (e20[-1], e50[-1], mac[-1], sig[-1]):
        return None
    return bool(e20[-1] > e50[-1] and mac[-1] > sig[-1])


def model_prob(M, op, v, btc, rs30, fng, h4, fee):
    if not M or not M.get("live"):
        return None
    L = M["live"]
    tp, sp = op["tg"] / op["en"] - 1, 1 - op["sl"] / op["en"]
    be = (sp + fee) / (tp + sp)
    p = op["p"] / 100
    x = [p, p - be, max(-20, min(20, op.get("ev") or 0)) / 10, (v.get("sc") or 0) / 5, (v.get("r") or 50) / 100,
         1.0 if btc == "naik" else 0.0, 1.0 if btc == "turun" else 0.0, max(-100, min(100, rs30 or 0)) / 100,
         (fng if fng is not None else 50) / 100, 1.0 if h4 is True else 0.0, 1.0 if h4 is None else 0.0,
         *[1.0 if op["k"] == k else 0.0 for k in ("pb", "gc", "mc", "os")]]
    z = L["w"][0] + sum(w * (xi - mu) / sd for w, xi, mu, sd in zip(L["w"][1:], x, L["mu"], L["sd"]))
    return round(100 / (1 + math.exp(-z)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site", "data"))
    a = ap.parse_args()
    M = json.load(open(os.path.join(a.out, "market.json")))
    st = M["stocks"]
    up = (M["meta"].get("klci") or {}).get("up")
    btc = "naik" if up == 1 else "turun" if up == -1 else "datar"
    fng = fear_greed()
    try:
        R = json.load(open(os.path.join(ROOT, "data", "research.json")))
        model = R.get("model")
    except Exception:
        model = None
    fee = M["meta"].get("bt", {}).get("fee", 0.002)
    bsp = (st.get("BTC") or {}).get("sp") or []
    coins = {}
    for c, v in st.items():
        sp = v.get("sp") or []
        x = {}
        if len(sp) > 31 and len(bsp) > 31 and sp[-31] and bsp[-31]:
            x["rs30"] = round((sp[-1] / sp[-31] - 1) * 100 - (bsp[-1] / bsp[-31] - 1) * 100, 1)
        x["h4"] = h4_from_intra(os.path.join(a.out, "i", f"{c}.json"))
        x.update(okx(c))
        if v.get("op"):
            x["pm"] = {o["k"]: model_prob(model, o, v, btc, x.get("rs30"), fng and fng["v"], x["h4"], fee) for o in v["op"]}
        coins[c] = x
    out = {"asof": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "btc": btc, "fng": fng,
           "model": bool(model and model.get("live")), "coins": coins}
    json.dump(out, open(os.path.join(a.out, "features.json"), "w"), separators=(",", ":"))
    json.dump(out, open(os.path.join(ROOT, "data", "features.json"), "w"), separators=(",", ":"))
    print(f"✓ Ciri isyarat: {len(coins)} coin · BTC {btc} · F&G {fng and fng['v']} · "
          f"4 jam {sum(1 for x in coins.values() if x.get('h4') is not None)} · funding {sum(1 for x in coins.values() if 'fund' in x)}")


if __name__ == "__main__":
    main()
