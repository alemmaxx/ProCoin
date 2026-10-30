"""Strategi crypto untuk diuji (dan digunakan jika terbukti) — data harian.

Setiap strategi: isyarat masuk pada penutup hari t, beli pada harga BUKA hari t+1.
Keluar ikut peraturan strategi (trailing stop ATR, isyarat keluar, atau had hari). Kos pergi-balik FEE ditolak.
Satu posisi pada satu masa bagi setiap coin & strategi (tiada isyarat bertindih).
"""
from common import ema, rsi
from backtest import atr, FEE


def _sim_trail(t, o, h, l, c, A, k, max_days, exit_fn=None):
    """Trailing stop: henti awal = beli − k×ATR; naik ikut harga tertinggi sejak beli − k×ATR (tidak pernah turun)."""
    n = len(c)
    if t + 1 >= n or A[t] is None:
        return None
    e = o[t + 1] or c[t]
    a = A[t]
    stop = e - k * a
    hi = e
    for j in range(t + 1, min(n, t + 1 + max_days)):
        if l[j] <= stop:
            x = min(o[j], stop) if j > t + 1 else stop
            return {"t": t, "days": j - t, "ret": x / e - 1 - FEE, "exit": j}
        hi = max(hi, h[j])
        stop = max(stop, hi - k * a)
        if exit_fn and exit_fn(j):
            if j + 1 < n:
                return {"t": t, "days": j + 1 - t, "ret": (o[j + 1] or c[j]) / e - 1 - FEE, "exit": j + 1}
            return None
    if t + max_days < n:
        j = t + max_days
        return {"t": t, "days": max_days, "ret": c[j] / e - 1 - FEE, "exit": j}
    return None  # masih terbuka


def run_strategy(key, o, h, l, c, v, btc_ok=None):
    """Pulangkan (senarai dagangan selesai, isyarat aktif hari terakhir atau None, posisi terbuka atau None)."""
    n = len(c)
    A = atr(h, l, c)
    e5, e20, e50, e200 = ema(c, 5), ema(c, 20), ema(c, 50), ema(c, 200)
    r2 = rsi(c, 2)
    S = STRATS[key]
    trades, t, open_pos = [], 1, None
    entry = S["entry"]
    while t < n:
        if A[t] is not None and entry(t, c, h, l, e5, e20, e50, e200, r2) and (btc_ok is None or not S.get("btc") or btc_ok(t)):
            ex = S.get("exit")
            exit_fn = (lambda j: ex(j, c, e5, e20, e50)) if ex else None
            tr = _sim_trail(t, o, h, l, c, A, S["k"], S["max"], exit_fn)
            if tr is None:
                open_pos = {"t": t, "atr": A[t]}
                break
            trades.append(tr)
            t = tr["exit"] + 1
            continue
        t += 1
    active = None
    L = n - 1
    if open_pos is None and A[L] is not None and entry(L, c, h, l, e5, e20, e50, e200, r2) and \
            (btc_ok is None or not S.get("btc") or btc_ok(L)):
        active = {"t": L, "atr": A[L]}
    return trades, active, open_pos


def _hh(h, t, w):
    return max(h[t - w:t]) if t >= w else None


STRATS = {
    "brk20": {"name": "Breakout 20 hari + trailing stop 3× ATR", "k": 3.0, "max": 120,
              "entry": lambda t, c, h, l, e5, e20, e50, e200, r2: t >= 20 and c[t] > _hh(h, t, 20)},
    "brk20f": {"name": "Breakout 20 hari, atas EMA200 + trailing 3× ATR", "k": 3.0, "max": 120,
               "entry": lambda t, c, h, l, e5, e20, e50, e200, r2: t >= 20 and e200[t] is not None and c[t] > e200[t] and c[t] > _hh(h, t, 20)},
    "brk20b": {"name": "Breakout 20 hari + BTC atas EMA200 + trailing 3× ATR", "k": 3.0, "max": 120, "btc": True,
               "entry": lambda t, c, h, l, e5, e20, e50, e200, r2: t >= 20 and c[t] > _hh(h, t, 20)},
    "brk55": {"name": "Breakout 55 hari + trailing stop 3× ATR", "k": 3.0, "max": 180,
              "entry": lambda t, c, h, l, e5, e20, e50, e200, r2: t >= 55 and c[t] > _hh(h, t, 55)},
    "brk55b": {"name": "Breakout 55 hari + BTC atas EMA200 + trailing 3× ATR", "k": 3.0, "max": 180, "btc": True,
               "entry": lambda t, c, h, l, e5, e20, e50, e200, r2: t >= 55 and c[t] > _hh(h, t, 55)},
    "ema": {"name": "EMA20 lintas atas EMA50 (atas EMA200) + trailing 3× ATR", "k": 3.0, "max": 180,
            "entry": lambda t, c, h, l, e5, e20, e50, e200, r2: None not in (e20[t], e50[t], e20[t - 1], e50[t - 1], e200[t])
            and e20[t - 1] <= e50[t - 1] and e20[t] > e50[t] and c[t] > e200[t],
            "exit": lambda j, c, e5, e20, e50: e20[j] is not None and e50[j] is not None and e20[j] < e50[j]},
    "rsi2": {"name": "RSI(2) bawah 10 dalam trend menaik (lantunan pendek)", "k": 2.5, "max": 10,
             "entry": lambda t, c, h, l, e5, e20, e50, e200, r2: r2[t] is not None and e200[t] is not None and r2[t] < 10 and c[t] > e200[t],
             "exit": lambda j, c, e5, e20, e50: e5[j] is not None and c[j] > e5[j]},
}
