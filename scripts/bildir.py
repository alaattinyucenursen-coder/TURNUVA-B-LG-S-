"""Yeni turnuvalar ve yaklaşan turnuvalar için bildirim gönderir.

Kanal ortam değişkenlerinden seçilir (GitHub'da Settings -> Secrets -> Actions):
- TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID: Telegram kanalına mesaj
- NTFY_TOPIC: ntfy.sh konusuna bildirim
Hiçbiri yoksa mesajlar sadece günlüğe yazılır.

Daha önce bildirilen turnuvalar data/bildirilen.json dosyasında tutulur, böylece aynı
turnuva iki kez "yeni" diye bildirilmez.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOURNAMENTS = ROOT / "web" / "tournaments.json"
SENT = ROOT / "data" / "bildirilen.json"
SITE = "https://alaattinyucenursen-coder.github.io/TURNUVA-B-LG-S-/"
REMIND_DAYS = 3
MAX_LEN = 3500  # Telegram sınırı 4096


def fmt_date(iso):
    d = date.fromisoformat(iso)
    months = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
    return f"{d.day} {months[d.month - 1]}"


def describe(t):
    when = fmt_date(t["start"]) if t["start"] == t["end"] else f"{fmt_date(t['start'])} – {fmt_date(t['end'])}"
    lines = [f"♞ {t['name']}", f"📅 {when}" + (f" · 📍 {t['city']}" if t.get("city") else "")]
    if t.get("categories"):
        lines.append("Kategoriler: " + ", ".join(c["name"] for c in t["categories"]))
    if t.get("prizes"):
        lines.append("🏆 " + " ".join(t["prizes"][:2]))
    if t.get("regulation"):
        lines.append(f"Yönerge: {t['regulation']}")
    return "\n".join(lines)


def build_messages(tournaments, sent, today):
    new = [t for t in tournaments if t["id"] not in sent]
    soon = [t for t in tournaments
            if t["start"] == (today + timedelta(days=REMIND_DAYS)).isoformat()
            and sent.get(t["id"], {}).get("reminded") != t["start"]]
    blocks = []
    if new:
        blocks.append(f"🆕 Yeni eklenen {len(new)} turnuva")
        blocks += [describe(t) for t in new]
    if soon:
        blocks.append(f"⏰ {REMIND_DAYS} gün sonra başlayan turnuvalar")
        blocks += [describe(t) for t in soon]
    if blocks:
        blocks.append(f"Tüm turnuvalar: {SITE}")
    # Uzun listeleri birden fazla mesaja böl
    messages, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 2 > MAX_LEN:
            messages.append(cur)
            cur = ""
        cur = (cur + "\n\n" + b).strip()
    if cur:
        messages.append(cur)
    return messages, new, soon


def send(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    topic = os.environ.get("NTFY_TOPIC")
    if token and chat:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=30)
        r.raise_for_status()
    elif topic:
        r = requests.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                          headers={"Title": "Satranç Turnuvaları", "Click": SITE}, timeout=30)
        r.raise_for_status()
    else:
        print("(bildirim kanalı ayarlı değil)")
    print(text, "\n---")


def main():
    today = date.today()
    tournaments = json.loads(TOURNAMENTS.read_text(encoding="utf-8"))["tournaments"]
    first_run = not SENT.exists()
    sent = {} if first_run else json.loads(SENT.read_text(encoding="utf-8"))

    if first_run:
        # İlk çalışmada mevcut listeyi "yeni" diye göndermeyelim
        sent = {t["id"]: {"end": t["end"]} for t in tournaments}
        print(f"İlk çalışma: {len(sent)} turnuva kaydedildi, bildirim gönderilmedi.")
    else:
        messages, new, soon = build_messages(tournaments, sent, today)
        for m in messages:
            send(m)
        for t in new:
            sent[t["id"]] = {"end": t["end"]}
        for t in soon:
            sent.setdefault(t["id"], {"end": t["end"]})["reminded"] = t["start"]
        print(f"{len(new)} yeni, {len(soon)} yaklaşan turnuva bildirildi.")

    # Biten turnuvaları kayıttan temizle
    sent = {k: v for k, v in sent.items() if v.get("end", "9999") >= today.isoformat()}
    SENT.write_text(json.dumps(sent, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
