"""Notifikasi Telegram ProCoin: isyarat aktif / pemerhatian baharu, isyarat tamat, dan Berita Berpotensi kukuh.

Rahsia GitHub (Settings → Secrets and variables → Actions):
  TELEGRAM_TOKEN    token bot dari @BotFather
  TELEGRAM_CHAT_ID  id chat anda (dari @userinfobot)
Tanpa rahsia ini skrip hanya rekod keadaan dan tidak hantar apa-apa.

Guna:
  python scripts/notify.py --kind signals --market _site/data/market.json
  python scripts/notify.py --kind news --market tmp/data/market.json --news data/news.json
  python scripts/notify.py --kind test
Keadaan (supaya tiada mesej berulang): data/notify-state.json
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
STATE = os.path.join(ROOT, "data", "notify-state.json")
APP = "https://alemmaxx.github.io/ProCoin/"
MYT = timezone(timedelta(hours=8))
NAME = {"drop2d": "Jatuh mendadak", "drop15": "Jatuh mendadak", "ema2050": "Trend EMA20×EMA50", "rsi2": "RSI 2", "brk20": "Breakout 20"}

# sama seperti app (index.html: NEWS_SPEC / NEWS_SOLID)
NEWS_SPEC = re.compile(r"\b(if|could|may|might|would|should|can|will|predict\w*|forecast\w*|expect\w*|eyes?|eyeing|target\w*|aims?|poised|set to|likely|"
                       r"possibl\w*|potential\w*|hopes?|rumou?r\w*|reportedly|analysts?|says?|said|why|how|what|when|whether|outlook|scenario|bull case|"
                       r"bear case|opinion|chance|odds|watch)\b|\?|price prediction|to the moon|\d+x\b", re.I)
NEWS_SOLID = re.compile(r"\b(approv\w*|inflows?|record|all-time high|new high|listing|listed|lists|partner\w*|launch\w*|integrat\w*|adopt\w*|buys|bought|"
                        r"acquir\w*|accumulat\w*|treasury|mainnet|upgrade[ds]?|surg\w*|soar\w*|jump\w*|rall(y|ies|ied)|breaks? (above|out)|tops|climbs?|gains?)\b", re.I)


def px(v):
    if v is None:
        return "-"
    v = float(v)
    if v >= 1000:
        return f"${v:,.2f}"
    if v >= 1:
        return f"${v:.3f}"
    return f"${v:.6g}"


def pct(a, b):
    return (a / b - 1) * 100 if a and b else None


def load(p, d=None):
    try:
        return json.load(open(p))
    except Exception:
        return d


def send(text):
    tok, chat = os.environ.get("TELEGRAM_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        print("  (tiada TELEGRAM_TOKEN / TELEGRAM_CHAT_ID — tidak dihantar)\n   " + text.replace("\n", "\n   "))
        return False
    import requests
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print("  ! Telegram gagal:", r.status_code, r.text[:200])
    return r.ok


def signals(M, st):
    meta, stocks = M["meta"], M["stocks"]
    asof = meta.get("asof") or max(v.get("d", "") for v in stocks.values())
    setups = meta.get("setups", {})
    seen = {}
    out = []
    for code, v in stocks.items():
        for o in v.get("op") or []:
            k, ago = o["k"], int(o.get("ago") or 0)
            sd = (date.fromisoformat(asof) - timedelta(days=ago)).isoformat()
            key = f"{code}:{k}"
            seen[key] = {"sd": sd, "en": o.get("en"), "g": o.get("g"), "n": v.get("n", code)}
            sid = f"sig:{key}:{sd}"
            if sid in st["sent"] or ago > 1:
                continue
            S = setups.get(k, {})
            nm = html.escape(v.get("n", code))
            if o.get("g") == "A":
                sp = v.get("sp") or []
                drop = pct(sp[-1], sp[-3]) if len(sp) >= 3 and ago == 0 else None
                sl = o.get("sl") or 0
                lines = [f"🟢 <b>Isyarat aktif: {nm} ({code})</b>",
                         f"{NAME.get(k, k)}" + (f": {drop:+.1f}% dalam 2 hari" if drop is not None else ""),
                         f"Harga tutup: {px(o.get('en'))}",
                         f"Keluar: harga tutup harian atas EMA10 (≈{px(o.get('tg'))}) atau 20 hari",
                         f"Cut loss: {px(sl)} ({pct(sl, o.get('en')):+.1f}%)" if sl else "",
                         f"Sejarah: {o.get('p')}% untung, purata {o.get('ev'):+}% ({o.get('n')} dagangan, 5 tahun)" if o.get("ev") is not None else ""]
            else:
                lines = [f"👀 <b>Pemerhatian: {nm} ({code})</b>",
                         f"{NAME.get(k, k)} — trend naik bermula",
                         f"Harga tutup: {px(o.get('en'))}",
                         "Keluar: bila EMA20 jatuh bawah EMA50 (pegang selagi trend kekal)",
                         f"Sejarah: {o.get('p')}% untung, purata {o.get('ev'):+}% ({o.get('n')} dagangan)" if o.get("ev") is not None else ""]
            out.append((sid, "\n".join(x for x in lines if x)))
    # isyarat yang tamat (ada semalam, tiada hari ini) — hanya yang pernah direkod
    for key, info in (st.get("open") or {}).items():
        if key in seen:
            continue
        code, k = key.split(":", 1)
        v = stocks.get(code, {})
        now = v.get("c")
        ch = pct(now, info.get("en"))
        sid = f"end:{key}:{info.get('sd')}"
        if sid in st["sent"]:
            continue
        icon = "🏁" if info.get("g") == "A" else "🔚"
        out.append((sid, f"{icon} <b>Isyarat tamat: {html.escape(info.get('n', code))} ({code})</b>\n{NAME.get(k, k)} (bermula {info.get('sd')})\n"
                         f"Harga tutup terkini: {px(now)}" + (f" ({ch:+.1f}% sejak isyarat, sebelum kos)" if ch is not None else "") +
                         "\nIkut peraturan strategi: masa untuk tutup / jual."))
    st["open"] = seen
    return out


def news(M, N, st):
    if not N or not N.get("items"):
        return []
    today = datetime.now(MYT).date().isoformat()
    stocks = (M or {}).get("stocks", {})
    out = []
    for code, arr in N["items"].items():
        td = [x for x in (arr or []) if x.get("d") == today]
        if any(x.get("x") == "-" for x in td):
            continue
        for x in td:
            t = x.get("t", "")
            if x.get("x") != "+" or NEWS_SPEC.search(t) or not NEWS_SOLID.search(t):
                continue
            sid = f"news:{code}:{x.get('u', t)[-60:]}"
            if sid in st["sent"]:
                continue
            nm = html.escape((stocks.get(code) or {}).get("n", code))
            out.append((sid, f"📰 <b>Berita Berpotensi: {nm} ({code})</b>\n{html.escape(t)}\n<i>{html.escape(x.get('s', ''))}</i> · <a href=\"{html.escape(x.get('u', APP))}\">baca</a>"))
    return out[:6]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["signals", "news", "test"], required=True)
    ap.add_argument("--market", default=os.path.join(ROOT, "_site", "data", "market.json"))
    ap.add_argument("--news", default=os.path.join(ROOT, "data", "news.json"))
    a = ap.parse_args()
    if a.kind == "test":
        ok = send(f"✅ <b>ProCoin bersambung</b>\nAnda akan terima isyarat aktif, pemerhatian, isyarat tamat dan Berita Berpotensi di sini.\n{APP}")
        sys.exit(0 if ok else 1)
    st = load(STATE, {}) or {}
    st.setdefault("sent", {})
    M = load(a.market)
    if not M:
        print("Tiada market.json — langkau")
        return
    msgs = signals(M, st) if a.kind == "signals" else news(M, load(a.news), st)
    first = not st.get("init")
    for sid, text in msgs:
        if first and sid.startswith("end:"):
            st["sent"][sid] = date.today().isoformat()
            continue
        if send(text + (f"\n{APP}" if not sid.startswith("news:") else "")) or not os.environ.get("TELEGRAM_TOKEN"):
            st["sent"][sid] = date.today().isoformat()
    st["init"] = 1
    cut = (date.today() - timedelta(days=45)).isoformat()
    st["sent"] = {k: v for k, v in st["sent"].items() if v >= cut}
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)
    print(f"✓ notifikasi {a.kind}: {len(msgs)} mesej")


if __name__ == "__main__":
    main()
