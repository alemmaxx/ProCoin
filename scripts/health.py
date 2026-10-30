"""Robot 8: pemantau kesihatan sistem ProCoin (setiap jam, GitHub sahaja).

Semak: data harga terkini, larian robot data/berita, dan laman app (GitHub Pages).
Tulis data/status.json (ringkas & awam — app tunjuk jalur amaran kepada pengguna).
Emel pilihan: tetapkan secret SMTP_USER, SMTP_PASS (cth. Gmail + App Password) dan ALERT_EMAIL.
Tanpa secret emel, semakan tetap berjalan dan GitHub sendiri akan emel anda bila robot gagal.
"""
import json
import os
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
STATUS = os.path.join(ROOT, "data", "status.json")
REPO = os.environ.get("GITHUB_REPOSITORY", "alemmaxx/ProCoin")
PAGES = "https://alemmaxx.github.io/ProCoin/"
MYT = timezone(timedelta(hours=8))
SLOW_S = 8.0


def now_myt():
    return datetime.now(MYT)


def expected_asof():
    """Bar harian UTC semalam sepatutnya ada selepas 03:00 UTC (11 pagi MYT); sebelum itu, kelmarin."""
    n = datetime.now(timezone.utc)
    d = n.date() - timedelta(days=1 if n.hour >= 3 else 2)
    return d.isoformat()


def check_data(issues):
    try:
        asof = json.load(open(os.path.join(ROOT, "data", "market-meta.json"))).get("asof", "")
    except Exception:
        asof = ""
    exp = expected_asof()
    if asof < exp:
        lag = (datetime.fromisoformat(exp).date() - datetime.fromisoformat(asof).date()).days if asof else 99
        issues.append({"k": "data", "pub": True, "lv": "down" if lag >= 2 else "warn",
                       "msg": f"Data harga lewat {lag} hari: terakhir {asof or '-'}, sepatutnya {exp}.",
                       "en": f"Price data {lag} day(s) late: last {asof or '-'}, expected {exp}."})
    return asof


def check_runs(issues, tok):
    if not tok:
        return
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    for wf, key, label in [("main.yml", "run_main", "Robot data harian"), ("news.yml", "run_news", "Robot berita")]:
        try:
            r = requests.get(f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/runs",
                             params={"per_page": 5, "status": "completed"}, headers=h, timeout=20)
            runs = [x for x in r.json().get("workflow_runs", []) if x.get("event") != "push"] or r.json().get("workflow_runs", [])
        except Exception as e:
            print(f"  {label}: status larian tidak dapat dibaca ({e})")
            continue
        if runs and runs[0].get("conclusion") not in ("success", "skipped", "cancelled"):
            issues.append({"k": key, "pub": False, "lv": "warn",
                           "msg": f"{label} gagal pada {runs[0].get('created_at', '')[:16]}Z ({runs[0].get('html_url')})."})


def check_site(issues):
    url = PAGES + "data/live.json"
    r, dt, err = None, 0.0, None
    for attempt in range(2):  # cuba dua kali supaya gangguan sekejap tidak dikira masalah
        t0 = time.time()
        try:
            r = requests.get(url, params={"t": int(t0)}, timeout=25)
            dt, err = time.time() - t0, None
            if r.ok and dt <= SLOW_S:
                break
        except Exception as e:
            err = e
        time.sleep(10)
    if err:
        issues.append({"k": "site", "pub": True, "lv": "down", "msg": f"Laman app tidak dapat dibuka ({type(err).__name__}).",
                       "en": f"App site could not be opened ({type(err).__name__})."})
    elif not r.ok:
        issues.append({"k": "site", "pub": True, "lv": "down", "msg": f"Laman app: HTTP {r.status_code}.", "en": f"App site: HTTP {r.status_code}."})
    elif dt > SLOW_S:
        issues.append({"k": "site_slow", "pub": True, "lv": "warn", "msg": f"Laman app perlahan ({dt:.1f}s).", "en": f"App site slow ({dt:.1f}s)."})


def send_mail(to, subject, body):
    user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    if not (user and pw and to):
        print("  emel dilangkau (tiada SMTP_USER/SMTP_PASS/ALERT_EMAIL)")
        return False
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, f"ProCoin Monitor <{user}>", to
    try:
        with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
            s.login(user, pw)
            s.sendmail(user, [x.strip() for x in to.split(",") if x.strip()], msg.as_string())
        print("  ✓ emel dihantar ke", to)
        return True
    except Exception as e:
        print("  ! emel gagal:", type(e).__name__, e)
        return False


def main():
    issues = []
    asof = check_data(issues)
    check_runs(issues, os.environ.get("GITHUB_TOKEN"))
    check_site(issues)
    old = json.load(open(STATUS)) if os.path.exists(STATUS) else {}
    # Elak amaran palsu: isu laman mesti berlaku 2 semakan berturut-turut. Isu data lewat terus dikira.
    raw = sorted(i["k"] for i in issues)
    seen_before = set(old.get("raw") or [])
    issues = [i for i in issues if i["k"] == "data" or i["k"] in seen_before]
    pub = [i for i in issues if i["pub"]]
    level = "down" if any(i["lv"] == "down" for i in pub) else ("warn" if pub else "ok")
    stamp = now_myt().isoformat(timespec="minutes")
    keys = sorted(i["k"] for i in issues)
    since = old.get("since") if old.get("level") == level and level != "ok" else (stamp if level != "ok" else None)
    new_status = {"level": level, "since": since, "keys": keys, "raw": raw}
    if {k: old.get(k) for k in new_status} != new_status:
        json.dump(new_status, open(STATUS, "w"), indent=1)
        print("status.json dikemas kini:", new_status)
    print(f"Tahap: {level} · isu disahkan: {keys or 'tiada'} · dikesan kali ini: {raw or 'tiada'} · data {asof}")
    for i in issues:
        print("  -", i["k"], "|", i["msg"])

    to = (os.environ.get("ALERT_EMAIL") or "").strip()
    prev, cur = set(old.get("keys") or []), set(keys)
    if cur - prev:
        body = "Masalah baharu dikesan oleh pemantau ProCoin:\n\n" + "\n".join(f"• {i['msg']}" for i in issues if i["k"] in cur - prev)
        body += f"\n\nMasa: {stamp} (MYT)\nApp: {PAGES}"
        send_mail(to, f"⚠️ ProCoin: {len(cur - prev)} masalah baharu", body)
    elif prev and not cur:
        send_mail(to, "✅ ProCoin: sistem pulih", f"Semua semakan kembali normal pada {stamp} (MYT).")


if __name__ == "__main__":
    main()
