"""Robot 3 (ProCoin): tarik tajuk berita crypto terkini (Google News RSS) untuk SEMUA coin dalam senarai.

Output: <out>/news.json dan data/news.json (disimpan dalam repo supaya berita lama dikekalkan).
Hanya tajuk, sumber, tarikh dan pautan disimpan — pengguna membaca berita penuh di laman asal.
Penanda nada (+ / − / ·) dikira dengan kata kunci ringkas, bukan analisa sentimen penuh.
"""
import argparse
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
STORE = os.path.join(ROOT, "data", "news.json")
KEEP_DAYS = 14
PER_STOCK = 8

POS = ["etf approval", "etf approved", "approves", "approved", "inflows", "inflow", "record high", "all-time high", "ath", "surge",
       "surges", "soars", "jumps", "rally", "rallies", "breakout", "bullish", "adoption", "partnership", "integrates", "launches",
       "upgrade", "listing", "lists", "buys", "accumulate", "accumulates", "treasury", "gains", "rises", "rebound", "recovers",
       "higher", "strong", "melonjak", "naik", "lulus"]
NEG = ["hack", "hacked", "exploit", "exploited", "stolen", "drained", "scam", "fraud", "lawsuit", "sues", "sued", "charges",
       "ban", "bans", "crackdown", "delist", "delisting", "outflows", "outflow", "liquidation", "liquidations", "crash", "crashes",
       "plunge", "plunges", "slump", "slumps", "tumbles", "dump", "dumps", "falls", "drops", "sell-off", "selloff", "bearish",
       "outage", "halt", "halts", "probe", "investigation", "warning", "lower", "weak", "jatuh", "merosot", "digodam"]


POS_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in POS) + r")\b")
NEG_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in NEG) + r")\b")


def tone(title):
    t = title.lower()
    p = bool(POS_RE.search(t))
    q = bool(NEG_RE.search(t))
    return "+" if p and not q else "-" if q and not p else "0"


def fetch(code, name, q):
    query = f'{q} (crypto OR cryptocurrency OR price OR token) when:{KEEP_DAYS}d'
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-MY&gl=MY&ceid=MY:en"
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (ProCoin news bot)"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    keys = [name.split()[0].lower()] + [w.lower() for w in q.split() if len(w) > 2]
    code_re = re.compile(r"\b" + re.escape(code) + r"\b")
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3].strip()
        if " price prediction" in title.lower():
            continue  # ramalan harga automatik, bukan berita
        tl = title.lower()
        if not (code_re.search(title) or any(k in tl for k in keys)):
            continue  # buang hasil yang tidak menyebut coin
        try:
            d = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone(timedelta(hours=8)))  # tarikh waktu Malaysia
        except Exception:
            continue
        out.append({"t": title, "s": src, "u": (it.findtext("link") or "").strip(), "d": d.strftime("%Y-%m-%d"), "x": tone(title)})
    out.sort(key=lambda x: x["d"], reverse=True)
    seen, res = set(), []
    for x in out:
        k = x["t"].lower()[:60]
        if k in seen:
            continue
        seen.add(k)
        res.append(x)
    return res[:PER_STOCK]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site", "data"))
    a = ap.parse_args()
    M = json.load(open(os.path.join(a.out, "market.json")))
    stocks = M["stocks"]
    old = json.load(open(STORE)) if os.path.exists(STORE) else {"items": {}}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")

    coins = {x["code"]: x for x in json.load(open(os.path.join(ROOT, "data", "coins.json")))}
    codes = [c for c in stocks if c in coins]

    items = {c: [x for x in v if x["d"] >= cutoff] for c, v in old.get("items", {}).items()}
    ok = fail = 0
    for c in codes:
        nm = coins[c]["name"]
        try:
            got = fetch(c, nm, coins[c].get("q") or nm)
            merged = got + [x for x in items.get(c, []) if x["t"] not in {g["t"] for g in got}]
            items[c] = sorted(merged, key=lambda x: x["d"], reverse=True)[:PER_STOCK]
            ok += 1
        except Exception as e:
            fail += 1
            print("  gagal", c, nm, e)
        time.sleep(0.8)
    items = {c: v for c, v in items.items() if v}
    out = {"asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "items": items}
    json.dump(out, open(os.path.join(a.out, "news.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(out, open(STORE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"✓ Berita: {ok} coin disemak, {fail} gagal, {len(items)} coin ada berita")


if __name__ == "__main__":
    main()
