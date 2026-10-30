"""Kajian penerokaan: cari isyarat yang BOLEH untung selepas kos sebenar runcit (Luno/HATA ≈1.2% pergi-balik).

Kaedah jujur (elak "overfit"):
  * Semua strategi berperaturan tetap & ada alasan ekonomi (trend, momentum, lantunan).
  * Tempoh REKA BENTUK = data lama (sebelum 24 bulan terakhir). Strategi hanya "layak" jika untung di sini.
  * Tempoh UJIAN = 24 / 12 / 6 bulan terakhir — tidak digunakan untuk memilih. Inilah ukuran sebenar.
  * Masuk pada harga BUKA hari selepas isyarat; keluar pada harga BUKA hari selepas isyarat keluar (atau stop).
  * Simulasi portfolio sama seperti Robot Auto: modal dibahagi 5, satu posisi setiap coin.

Output: data/explore.json
"""
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import market  # noqa: E402
from common import ema, rsi  # noqa: E402
from backtest import atr  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "data", "explore.json")
COSTS = (0.2, 1.2)          # % pergi-balik: backtest asal vs kos sebenar Luno/HATA (yuran + spread)
BIG = {"BTC", "ETH", "XRP", "BNB", "SOL"}


def sma(v, n):
    o, s = [None] * len(v), 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n:
            s -= v[i - n]
        if i >= n - 1:
            o[i] = s / n
    return o


def hh(a, t, n):
    return max(a[t - n:t]) if t >= n else None


def ll(a, t, n):
    return min(a[t - n:t]) if t >= n else None


def crossed_up(x, y, t):
    return t > 0 and None not in (x[t], y[t], x[t - 1], y[t - 1]) and x[t - 1] <= y[t - 1] and x[t] > y[t]


class D:
    """Siri harga satu coin + indicator."""
    def __init__(self, rows, btc_up):
        self.d = [r[0] for r in rows]
        self.o = [float(r[1] or r[4]) for r in rows]
        self.h = [float(r[2] or r[4]) for r in rows]
        self.l = [float(r[3] or r[4]) for r in rows]
        self.c = [float(r[4]) for r in rows]
        c = self.c
        self.e5, self.e10, self.e20, self.e50, self.e100, self.e200 = (ema(c, n) for n in (5, 10, 20, 50, 100, 200))
        self.s20 = sma(c, 20)
        self.r2, self.r14 = rsi(c, 2), rsi(c, 14)
        self.A = atr(self.h, self.l, self.c)
        self.bu = [btc_up.get(x, False) for x in self.d]
        sd = [None] * len(c)
        for i in range(19, len(c)):
            w = c[i - 19:i + 1]
            m = sum(w) / 20
            sd[i] = math.sqrt(sum((x - m) ** 2 for x in w) / 20)
        self.sd20 = sd


def first_of_month(x, t):
    return t > 0 and x.d[t][:7] != x.d[t - 1][:7]


def monday(x, t):
    return date.fromisoformat(x.d[t]).weekday() == 0


def ret_n(x, t, n):
    return x.c[t] / x.c[t - n] - 1 if t >= n else None


# Setiap strategi: entry(x,t) pada tutup hari t; exit(x,j,e_idx) pada tutup hari j; stop=(k ATR, trailing?) ; max hari
STRATS = {
    # --- trend (jarang berdagang)
    "t_ema50x": ("Harga lintas atas EMA50 (EMA50>EMA200), keluar bawah EMA50",
                 lambda x, t: crossed_up(x.c, x.e50, t) and x.e200[t] is not None and x.e50[t] > x.e200[t],
                 lambda x, j, e: x.c[j] < x.e50[j], None, 365),
    "t_golden": ("Golden cross EMA50/EMA200, keluar death cross",
                 lambda x, t: crossed_up(x.e50, x.e200, t), lambda x, j, e: x.e50[j] < x.e200[j], None, 730),
    "t_e200": ("Harga lintas atas EMA200, keluar bawah EMA200",
               lambda x, t: crossed_up(x.c, x.e200, t), lambda x, j, e: x.c[j] < x.e200[j], None, 730),
    "t_e100b": ("Harga lintas atas EMA100 + BTC naik, keluar bawah EMA100",
                lambda x, t: crossed_up(x.c, x.e100, t) and x.bu[t], lambda x, j, e: x.c[j] < x.e100[j], None, 730),
    "t_e20_50": ("EMA20 lintas atas EMA50 (atas EMA200), keluar EMA20<EMA50",
                 lambda x, t: crossed_up(x.e20, x.e50, t) and x.e200[t] is not None and x.c[t] > x.e200[t],
                 lambda x, j, e: x.e20[j] < x.e50[j], None, 365),
    "t_e20_50b": ("EMA20 lintas atas EMA50 + BTC naik, keluar EMA20<EMA50",
                  lambda x, t: crossed_up(x.e20, x.e50, t) and x.bu[t], lambda x, j, e: x.e20[j] < x.e50[j], None, 365),
    # --- Donchian / breakout (turtle)
    "d20_10": ("Breakout 20 hari, keluar bawah paras rendah 10 hari",
               lambda x, t: t >= 20 and x.c[t] > hh(x.h, t, 20), lambda x, j, e: x.c[j] < ll(x.l, j, 10), None, 365),
    "d55_20": ("Breakout 55 hari, keluar bawah paras rendah 20 hari",
               lambda x, t: t >= 55 and x.c[t] > hh(x.h, t, 55), lambda x, j, e: x.c[j] < ll(x.l, j, 20), None, 365),
    "d55_20b": ("Breakout 55 hari + BTC naik, keluar bawah rendah 20 hari",
                lambda x, t: t >= 55 and x.c[t] > hh(x.h, t, 55) and x.bu[t], lambda x, j, e: x.c[j] < ll(x.l, j, 20), None, 365),
    "d100_50": ("Breakout 100 hari, keluar bawah paras rendah 50 hari",
                lambda x, t: t >= 100 and x.c[t] > hh(x.h, t, 100), lambda x, j, e: x.c[j] < ll(x.l, j, 50), None, 730),
    "d100_50b": ("Breakout 100 hari + BTC naik, keluar bawah rendah 50 hari",
                 lambda x, t: t >= 100 and x.c[t] > hh(x.h, t, 100) and x.bu[t], lambda x, j, e: x.c[j] < ll(x.l, j, 50), None, 730),
    "b20_k3": ("Breakout 20 hari + trailing 3× ATR (sistem sekarang)",
               lambda x, t: t >= 20 and x.c[t] > hh(x.h, t, 20), None, (3.0, True), 120),
    "b20_k5": ("Breakout 20 hari + trailing 5× ATR",
               lambda x, t: t >= 20 and x.c[t] > hh(x.h, t, 20), None, (5.0, True), 365),
    "b55_k5b": ("Breakout 55 hari + BTC naik + trailing 5× ATR",
                lambda x, t: t >= 55 and x.c[t] > hh(x.h, t, 55) and x.bu[t], None, (5.0, True), 365),
    # --- momentum masa (tempoh tetap)
    "m_month": ("Awal bulan: momentum 90 hari positif + atas EMA200 + BTC naik, pegang 1 bulan",
                lambda x, t: first_of_month(x, t) and ret_n(x, t, 90) is not None and ret_n(x, t, 90) > 0
                and x.e200[t] is not None and x.c[t] > x.e200[t] and x.bu[t],
                lambda x, j, e: j > e and first_of_month(x, j), None, 40),
    "m_month30": ("Awal bulan: momentum 30 hari positif + BTC naik, pegang 1 bulan",
                  lambda x, t: first_of_month(x, t) and ret_n(x, t, 30) is not None and ret_n(x, t, 30) > 0 and x.bu[t],
                  lambda x, j, e: j > e and first_of_month(x, j), None, 40),
    "m_week": ("Isnin: momentum 28 hari positif + BTC naik, pegang 1 minggu",
               lambda x, t: monday(x, t) and ret_n(x, t, 28) is not None and ret_n(x, t, 28) > 0 and x.bu[t],
               lambda x, j, e: j >= e + 6, None, 10),
    # --- lantunan (mean reversion) versi lebih ketat / pegang lebih lama
    "r2_10": ("RSI(2)<10 atas EMA200, keluar atas EMA5 (sistem sekarang)",
              lambda x, t: x.r2[t] is not None and x.e200[t] is not None and x.r2[t] < 10 and x.c[t] > x.e200[t],
              lambda x, j, e: x.c[j] > x.e5[j], (2.5, False), 10),
    "r2_5b": ("RSI(2)<5 atas EMA200 + BTC naik, keluar atas EMA5",
              lambda x, t: x.r2[t] is not None and x.e200[t] is not None and x.r2[t] < 5 and x.c[t] > x.e200[t] and x.bu[t],
              lambda x, j, e: x.c[j] > x.e5[j], (2.5, False), 10),
    "r2_10l": ("RSI(2)<10 atas EMA200, keluar atas EMA20 (pegang lebih lama)",
               lambda x, t: x.r2[t] is not None and x.e200[t] is not None and x.r2[t] < 10 and x.c[t] > x.e200[t],
               lambda x, j, e: x.c[j] > x.e20[j] and j > e + 2, (3.0, False), 30),
    "r14_30": ("RSI(14)<30 atas EMA200 (jarang), keluar RSI(14)>55",
               lambda x, t: x.r14[t] is not None and x.e200[t] is not None and x.r14[t] < 30 and x.c[t] > x.e200[t],
               lambda x, j, e: x.r14[j] > 55, (3.0, False), 40),
    "drop15": ("Jatuh >15% dalam 3 hari dalam trend naik (EMA200), keluar atas EMA10",
               lambda x, t: t >= 3 and x.e200[t] is not None and x.c[t] > x.e200[t] and x.c[t] / x.c[t - 3] - 1 < -0.15,
               lambda x, j, e: x.c[j] > x.e10[j], (3.0, False), 20),
    "bb_low": ("Tutup bawah Bollinger bawah dalam trend naik, keluar di garis tengah",
               lambda x, t: x.sd20[t] is not None and x.e200[t] is not None and x.c[t] > x.e200[t] and x.c[t] < x.s20[t] - 2 * x.sd20[t],
               lambda x, j, e: x.c[j] > x.s20[j], (3.0, False), 20),
    "dip_bull": ("Pullback ke EMA50 dalam trend kuat (EMA50>EMA200, BTC naik), keluar tutup atas paras tinggi 10 hari",
                 lambda x, t: None not in (x.e50[t], x.e200[t]) and x.e50[t] > x.e200[t] and x.bu[t] and x.l[t] <= x.e50[t] < x.c[t]
                 and t > 0 and x.c[t - 1] > x.e50[t - 1],
                 lambda x, j, e: x.c[j] > hh(x.h, j, 10), (2.5, False), 30),
}


def sim(x, entry, exit_fn, stop, max_days, start_t):
    """Satu posisi pada satu masa. Pulangkan dagangan: [hari isyarat, hari masuk, hari keluar, pulangan kasar %, terbuka?]."""
    n, tr, t = len(x.c), [], max(start_t, 201)
    while t < n - 1:
        try:
            ok = entry(x, t)
        except (TypeError, ZeroDivisionError):
            ok = False
        if not ok or x.A[t] is None:
            t += 1
            continue
        e_i = t + 1
        e = x.o[e_i] or x.c[t]
        st = e - stop[0] * x.A[t] if stop else None
        hi = e
        out = None
        for j in range(e_i, n):
            if st is not None and x.l[j] <= st:
                px = min(x.o[j], st) if j > e_i else st
                out = (j, px)
                break
            if stop and stop[1]:
                hi = max(hi, x.h[j])
                st = max(st, hi - stop[0] * x.A[t])
            done = j - e_i + 1 >= max_days
            if not done and exit_fn:
                try:
                    done = bool(exit_fn(x, j, e_i))
                except (TypeError, ZeroDivisionError):
                    done = False
            if done:
                if j + 1 < n:
                    out = (j + 1, x.o[j + 1] or x.c[j])
                break
        if out is None:  # masih terbuka hari ini
            tr.append([t, e_i, n - 1, (x.c[-1] / e - 1) * 100, 1])
            break
        tr.append([t, e_i, out[0], (out[1] / e - 1) * 100, 0])
        t = out[0]
    return tr


def summ(rets):
    n = len(rets)
    if not n:
        return {"n": 0}
    pos, neg = sum(r for r in rets if r > 0), -sum(r for r in rets if r < 0)
    avg = sum(rets) / n
    sd = math.sqrt(sum((r - avg) ** 2 for r in rets) / (n - 1)) if n > 1 else 0
    return {"n": n, "win": round(sum(1 for r in rets if r > 0) / n * 100, 1), "avg": round(avg, 2),
            "med": round(sorted(rets)[n // 2], 2), "pf": round(pos / neg, 2) if neg else None,
            "ci": round(1.96 * sd / math.sqrt(n), 2) if n > 1 else None}


def portfolio(trades, d0, d1, cost):
    """Robot Auto: modal 1, setiap posisi 20% nilai semasa, satu posisi setiap coin. Dagangan = dict(c,in,out,g,open)."""
    T = sorted([t for t in trades if d0 <= t["in"] <= d1], key=lambda t: (t["in"], t["c"]))
    free = eq = 1.0
    held, ex, peak, mdd, taken, inmkt = set(), [], 1.0, 0.0, 0, 0.0

    def settle(d):
        nonlocal free, eq, peak, mdd
        ex.sort(key=lambda y: y["out"])
        while ex and ex[0]["out"] <= d and not ex[0]["open"]:
            y = ex.pop(0)
            pl = y["amt"] * (y["g"] - cost) / 100
            free += y["amt"] + pl
            eq += pl
            held.discard(y["c"])
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak * 100)
    for t in T:
        settle(t["in"])
        if t["c"] in held:
            continue
        per = eq / 5
        amt = per if free >= per else (free if free >= per * 0.5 else None)
        if amt is None:
            continue
        free -= amt
        held.add(t["c"])
        taken += 1
        y = dict(t, amt=amt)
        ex.append(y)
        inmkt += amt * max(1, (date.fromisoformat(min(t["out"], d1)) - date.fromisoformat(t["in"])).days)
    settle("9999")
    unreal = sum(y["amt"] * (y["g"] - cost) / 100 for y in ex)
    span = max(1, (date.fromisoformat(d1) - date.fromisoformat(d0)).days)
    return {"ret": round((eq + unreal - 1) * 100, 1), "mdd": round(mdd, 1), "n": taken, "exp": round(inmkt / span * 100)}


def main():
    coins = market.load_coins()
    print(f"Penerokaan: tarik harga harian {len(coins)} coin …")
    px = market.prices_yf(coins)
    today_utc = datetime.now(timezone.utc).date().isoformat()
    px = {c: [r for r in rows if r[0] < today_utc] for c, rows in px.items() if len(rows) > 400}
    btc = px["BTC"]
    bc = [float(r[4]) for r in btc]
    be = ema(bc, 200)
    btc_up = {r[0]: (be[i] is not None and bc[i] > be[i]) for i, r in enumerate(btc)}
    end = btc[-1][0]
    E = date.fromisoformat(end)
    P = {"6m": (E - timedelta(days=182)).isoformat(), "12m": (E - timedelta(days=365)).isoformat(),
         "24m": (E - timedelta(days=730)).isoformat()}
    start = btc[0][0]
    design = (start, P["24m"])  # REKA BENTUK: sebelum 24 bulan terakhir
    series = {c: D(rows, btc_up) for c, rows in px.items()}
    print(f"  data {start} → {end}; reka bentuk hingga {P['24m']}")

    def hold(code, d0):
        rows = [r for r in px.get(code, []) if r[0] >= d0]
        return round((float(rows[-1][4]) / float(rows[0][4]) - 1) * 100, 1) if rows else None

    res = []
    for key, (name, en, exf, stop, mx) in STRATS.items():
        trades = []
        for code, x in series.items():
            for t0, ei, xo, g, op in sim(x, en, exf, stop, mx, 201):
                trades.append({"c": code, "sig": x.d[t0], "in": x.d[ei], "out": x.d[xo], "g": g, "open": op,
                               "days": xo - ei})
        done = [t for t in trades if not t["open"]]
        row = {"key": key, "name": name, "trades_total": len(trades),
               "tl": [[t["c"], t["in"], t["out"], round(t["g"], 2), t["open"]] for t in sorted(trades, key=lambda t: t["in"]) if t["in"] >= P["24m"]]}
        for cost in COSTS:
            ck = f"c{cost}"
            rows = {}
            for lbl, (d0, d1) in {"design": design, "24m": (P["24m"], end), "12m": (P["12m"], end), "6m": (P["6m"], end),
                                  "all": (start, end)}.items():
                sel = [t["g"] - cost for t in done if d0 <= t["in"] < d1 or (lbl != "design" and d0 <= t["in"] <= d1)]
                s = summ(sel)
                s["pf_port"] = portfolio(trades, d0, d1, cost)
                big = [t["g"] - cost for t in done if t["c"] in BIG and d0 <= t["in"] <= d1]
                s["big"] = summ(big)
                s["days"] = round(sum(t["days"] for t in done if d0 <= t["in"] <= d1) / max(1, len(sel)), 1)
                rows[lbl] = s
            yrs = {}
            for t in done:
                yrs.setdefault(t["in"][:4], []).append(t["g"] - cost)
            rows["years"] = {y: summ(v) for y, v in sorted(yrs.items())}
            dz = rows["design"]
            # LAYAK = untung dalam tempoh reka bentuk sahaja (keputusan ujian TIDAK digunakan untuk memilih)
            rows["eligible"] = bool(dz["n"] >= 30 and (dz.get("avg") or 0) > 0 and (dz.get("pf") or 0) >= 1.2)
            # LULUS = layak DAN kekal untung dalam ujian 24 bulan terakhir
            t24 = rows["24m"]
            rows["passed"] = bool(rows["eligible"] and t24["n"] >= 15 and (t24.get("avg") or 0) > 0 and (t24.get("pf") or 0) >= 1.1)
            row[ck] = rows
        res.append(row)
        c1 = row["c1.2"]
        print(f"  {key:10s} n={len(done):4d} | kos 1.2: reka {c1['design'].get('avg')}% pf {c1['design'].get('pf')} "
              f"| 24m {c1['24m'].get('avg')}% | 12m {c1['12m'].get('avg')}% port {c1['12m']['pf_port']['ret']}% | lulus {c1['passed']}")
    out = {"asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "start": start, "end": end, "design_end": P["24m"],
           "periods": P, "costs": COSTS, "coins": len(px), "big": sorted(BIG),
           "hold": {k: {"BTC": hold("BTC", v), "ETH": hold("ETH", v)} for k, v in {**P, "design": start}.items()},
           "strats": res}
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"✓ {OUT}")


if __name__ == "__main__":
    main()
