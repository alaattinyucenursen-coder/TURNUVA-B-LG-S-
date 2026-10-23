"""Turnuva verisini toplar ve web/tournaments.json dosyasını yeniden yazar.

Kaynaklar:
- chess-results.com Türkiye listesi: turnuva adı, tarih, yer, kategoriler (sadece bağlantı
  için gereken temel bilgi; oyuncu listesi, eşleşme ve sonuç kopyalanmaz).
- tsf.org.tr etkinlik takvimi: resmi ulusal ve uluslararası turnuvalar.
- data/ekler.json: elle ya da yönergelerden eklenen ödül, kayıt ve yönerge bilgileri.

Biten turnuvalar dosyaya yazılmaz, böylece uygulamadan kendiliğinden düşer.
"""

import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "tournaments.json"
EXTRAS = ROOT / "data" / "ekler.json"

CR = "https://chess-results.com/"
TSF = "https://www.tsf.org.tr/"
MAX_CR_TOURNAMENTS = 80
DEBUG = "--debug" in sys.argv

session = requests.Session()
session.headers["User-Agent"] = "SatrancTurnuvalari/0.1 (+https://github.com/alaattinyucenursen-coder/TURNUVA-B-LG-S-)"

PROVINCES = """Adana Adıyaman Afyonkarahisar Ağrı Aksaray Amasya Ankara Antalya Ardahan Artvin Aydın Balıkesir
Bartın Batman Bayburt Bilecik Bingöl Bitlis Bolu Burdur Bursa Çanakkale Çankırı Çorum Denizli Diyarbakır Düzce
Edirne Elazığ Erzincan Erzurum Eskişehir Gaziantep Giresun Gümüşhane Hakkari Hatay Iğdır Isparta İstanbul İzmir
Kahramanmaraş Karabük Karaman Kars Kastamonu Kayseri Kilis Kırıkkale Kırklareli Kırşehir Kocaeli Konya Kütahya
Malatya Manisa Mardin Mersin Muğla Muş Nevşehir Niğde Ordu Osmaniye Rize Sakarya Samsun Şanlıurfa Siirt Sinop
Sivas Şırnak Tekirdağ Tokat Trabzon Tunceli Uşak Van Yalova Yozgat Zonguldak""".split()

TR_MONTHS = {m: i for i, m in enumerate(
    "ocak şubat mart nisan mayıs haziran temmuz ağustos eylül ekim kasım aralık".split(), 1)}


def log(*a):
    print(*a, flush=True)


def get(url):
    time.sleep(1)  # sitelere yük bindirmemek için
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def upper_tr(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


def find_city(*texts):
    blob = upper_tr(" ".join(t for t in texts if t))
    for p in PROVINCES:
        if re.search(r"\b" + re.escape(upper_tr(p)) + r"\b", blob):
            return p
    return ""


def parse_dates(text):
    """'2026/10/24 to 2026/10/25' ya da '24.10.2026' gibi biçimlerden tarihleri çıkarır."""
    found = []
    for y, m, d in re.findall(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", text):
        found.append(date(int(y), int(m), int(d)))
    for d, m, y in re.findall(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text):
        found.append(date(int(y), int(m), int(d)))
    return found


# ---------- chess-results ----------

def cr_list():
    soup = get(CR + "fed.aspx?lan=1&fed=TUR")
    ids = []
    for a in soup.select("a[href]"):
        m = re.search(r"tnr(\d+)\.aspx", a["href"], re.I)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    log(f"chess-results: {len(ids)} turnuva bulundu")
    return ids[:MAX_CR_TOURNAMENTS]


def cr_details(tnr):
    url = f"{CR}tnr{tnr}.aspx?lan=1&turdet=YES"
    soup = get(url)
    if DEBUG and tnr == DEBUG_TNR[0]:
        log("---- DEBUG detay sayfası ----")
        for tr in soup.select("table tr")[:40]:
            log(" | ".join(td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"]))[:200])
        for sel in soup.select("select"):
            log("SELECT", sel.get("name"), [o.get_text(strip=True) for o in sel.find_all("option")][:10])
    name = ""
    h2 = soup.find("h2")
    if h2:
        name = h2.get_text(" ", strip=True)
    info = {}
    for tr in soup.select("table tr"):
        cells = tr.find_all("td")
        if len(cells) == 2:
            k = cells[0].get_text(" ", strip=True).rstrip(":").lower()
            info[k] = cells[1].get_text(" ", strip=True)

    def pick(*keys):
        for k in keys:
            for ik, v in info.items():
                if k in ik:
                    return v
        return ""

    dates = parse_dates(pick("date"))
    # Aynı turnuvanın diğer kategorileri (chess-results'ta her kategori ayrı turnuvadır)
    siblings = {}
    for a in soup.select("a[href]"):
        m = re.search(r"tnr(\d+)\.aspx\?lan=1&art=0", a["href"], re.I)
        if m:
            siblings[m.group(1)] = a.get_text(" ", strip=True)
    return {
        "tnr": tnr,
        "name": name,
        "organizer": pick("organizer"),
        "location": pick("location"),
        "rounds": pick("number of rounds"),
        "timeControl": pick("time control"),
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
        "siblings": siblings,
    }


def split_category(name):
    """'... TURNUVASI 08 YAŞ VE ALTI KATEGORİSİ' -> ('... TURNUVASI', '08 YAŞ VE ALTI')"""
    m = re.search(r"(TURNUVASI|ŞAMPİYONASI|BİRİNCİLİĞİ|LİGİ)\s+(.+)$", name, re.I)
    if m:
        base = name[: m.end(1)]
        cat = re.sub(r"\s*KATEGORİSİ\s*", " ", m.group(2), flags=re.I).strip()
        return base.strip(), cat
    return name.strip(), ""


def title_tr(s):
    small = {"ve", "ile", "de", "da"}
    words = s.replace("I", "ı").replace("İ", "i").lower().split()
    out = []
    for i, w in enumerate(words):
        if i and w in small:
            out.append(w)
        else:
            out.append(w[:1].replace("i", "İ").upper() + w[1:])
    return " ".join(out)


def collect_cr(today):
    groups = {}
    seen = set()
    for tnr in cr_list():
        if tnr in seen:
            continue
        try:
            d = cr_details(tnr)
        except Exception as e:  # tek turnuva hatası bütün işi durdurmasın
            log(f"  tnr{tnr}: hata {e}")
            continue
        seen.add(tnr)
        if not d["start"] or (d["end"] or d["start"]) < today:
            continue
        base, cat = split_category(d["name"])
        key = (upper_tr(base), d["start"])
        g = groups.setdefault(key, {
            "id": f"cr-{tnr}",
            "name": title_tr(base),
            "city": find_city(d["name"], d["location"], d["organizer"]),
            "start": d["start"].isoformat(),
            "end": (d["end"] or d["start"]).isoformat(),
            "type": "il",
            "timeControl": d["timeControl"],
            "rounds": int(d["rounds"]) if d["rounds"].isdigit() else None,
            "categories": [],
            "prizes": [],
            "source": "chess-results",
        })
        g["categories"].append({"name": title_tr(cat) or "Genel",
                                "url": f"{CR}tnr{tnr}.aspx?lan=1"})
        log(f"  + {d['name']} ({d['start']})")
    return list(groups.values())


# ---------- TSF ----------

def collect_tsf(today):
    soup = get(TSF + "takvim")
    if DEBUG:
        log("---- DEBUG TSF takvim ----")
        a = soup.select_one("a[href*='/etkinlik/']")
        if a:
            box = a.find_parent(["article", "li", "div"])
            log(str(box)[:2500])
    events = {}
    for a in soup.select("a[href*='/etkinlik/']"):
        m = re.search(r"/etkinlik/(\d+)", a["href"])
        if not m or m.group(1) in events:
            continue
        box = a.find_parent(["article", "li"]) or a.find_parent("div")
        text = box.get_text(" ", strip=True) if box else a.get_text(" ", strip=True)
        events[m.group(1)] = (urljoin(TSF, a["href"]), a.get_text(" ", strip=True), text)

    out = []
    for eid, (url, title, text) in events.items():
        try:
            page = get(url)
        except Exception as e:
            log(f"  TSF {eid}: hata {e}")
            continue
        h1 = page.find("h1")
        name = h1.get_text(" ", strip=True) if h1 else title
        body = page.get_text(" ", strip=True)
        dates = tr_dates(body)
        if not dates:
            continue
        start, end = dates[0], dates[-1] if len(dates) > 1 else dates[0]
        if end < today:
            continue
        intl = "uluslararası" in body.lower() and "ulusal etkinlik" not in body.lower()
        site = page.select_one("a[href*='.tsf.org.tr']:not([href*='www.tsf'])")
        out.append({
            "id": f"tsf-{eid}",
            "name": name,
            "city": find_city(name, text),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "type": "uluslararası" if intl else "ulusal",
            "categories": [],
            "prizes": [],
            "regulation": url,
            **({"website": site["href"]} if site else {}),
            "source": "tsf",
        })
        log(f"  + TSF {name} ({start})")
    return out


def tr_dates(text):
    """'3 Aralık 2026' ve '3 - 14 Aralık 2026' biçimlerini okur."""
    res = []
    for d1, d2, mon, y in re.findall(
            r"(\d{1,2})\s*(?:[-–]\s*(\d{1,2}))?\s+(" + "|".join(TR_MONTHS) + r")\s+(\d{4})", text, re.I):
        m = TR_MONTHS[mon.lower().replace("I", "ı")]
        res.append(date(int(y), m, int(d1)))
        if d2:
            res.append(date(int(y), m, int(d2)))
        if len(res) >= 2:
            break
    return sorted(res)


# ---------- birleştirme ----------

def main():
    today = date.today()
    tournaments = []
    for name, fn in (("chess-results", collect_cr), ("TSF", collect_tsf)):
        try:
            tournaments += fn(today)
        except Exception as e:
            log(f"{name} kaynağı okunamadı: {e}")

    extras = json.loads(EXTRAS.read_text(encoding="utf-8")) if EXTRAS.exists() else {}
    for t in tournaments:
        t.update(extras.get(t["id"], {}))

    if not tournaments and OUT.exists():
        log("Hiç turnuva toplanamadı, eski dosya korunuyor.")
        sys.exit(1)

    tournaments.sort(key=lambda t: t["start"])
    OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tournaments": tournaments,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Toplam {len(tournaments)} turnuva yazıldı.")


DEBUG_TNR = [None]

if __name__ == "__main__":
    if DEBUG:
        _orig = cr_list

        def cr_list():  # noqa: F811
            ids = _orig()
            DEBUG_TNR[0] = ids[0] if ids else None
            return ids
    main()
