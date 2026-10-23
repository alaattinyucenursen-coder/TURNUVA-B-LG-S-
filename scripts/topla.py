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

session = requests.Session()
session.headers["User-Agent"] = "SatrancTurnuvalari/0.1 (+https://github.com/alaattinyucenursen-coder/TURNUVA-B-LG-S-)"

PROVINCES = """Adana Adıyaman Afyonkarahisar Ağrı Aksaray Amasya Ankara Antalya Ardahan Artvin Aydın Balıkesir
Bartın Batman Bayburt Bilecik Bingöl Bitlis Bolu Burdur Bursa Çanakkale Çankırı Çorum Denizli Diyarbakır Düzce
Edirne Elazığ Erzincan Erzurum Eskişehir Gaziantep Giresun Gümüşhane Hakkari Hatay Iğdır Isparta İstanbul İzmir
Kahramanmaraş Karabük Karaman Kars Kastamonu Kayseri Kilis Kırıkkale Kırklareli Kırşehir Kocaeli Konya Kütahya
Malatya Manisa Mardin Mersin Muğla Muş Nevşehir Niğde Ordu Osmaniye Rize Sakarya Samsun Şanlıurfa Siirt Sinop
Sivas Şırnak Tekirdağ Tokat Trabzon Tunceli Uşak Van Yalova Yozgat Zonguldak""".split()

# Turnuva adlarında sık geçen ilçeler
DISTRICTS = {"Akhisar": "Manisa", "Manavgat": "Antalya", "Alanya": "Antalya", "Torbalı": "İzmir",
             "Anamur": "Mersin", "Tarsus": "Mersin", "Köyceğiz": "Muğla", "Bodrum": "Muğla",
             "Fethiye": "Muğla", "Burhaniye": "Balıkesir", "Ürgüp": "Nevşehir", "Çubuk": "Ankara",
             "Kuşadası": "Aydın", "Didim": "Aydın", "Çorlu": "Tekirdağ", "İnegöl": "Bursa",
             "Ereğli": "Zonguldak", "Iskenderun": "Hatay", "İskenderun": "Hatay"}

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
    """İl adını sırayla verilen metinlerde arar; önce turnuva adı gelmeli."""
    for t in texts:
        blob = upper_tr(t or "")
        for name, prov in [(p, p) for p in PROVINCES] + list(DISTRICTS.items()):
            if re.search(r"(?<!\w)" + re.escape(upper_tr(name)) + r"(?!\w)", blob):
                return prov
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
    return {
        "tnr": tnr,
        "name": name,
        "organizer": pick("organizer"),
        "location": pick("location"),
        "rounds": pick("number of rounds"),
        "timeControl": pick("time control"),
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
    }


def split_category(name):
    """'... TURNUVASI 08 YAŞ VE ALTI KATEGORİSİ' -> ('... TURNUVASI', '08 YAŞ VE ALTI')"""
    name = re.sub(r"[_\s]+", " ", name).strip()
    m = re.search(r"(TURNUVASI|ŞAMPİYONASI|BİRİNCİLİĞİ|LİGİ)\s+(.+)$", name, re.I)
    if not m:
        return name, ""
    cat = re.sub(r"\b(KATEGORİSİ|KATEGORİ|KTG)\b\.?", " ", m.group(2), flags=re.I)
    words = []
    for w in cat.split():
        if not words or w.lower() != words[-1].lower():  # "U8 U8" gibi tekrarları at
            words.append(w)
    return name[: m.end(1)].strip(), " ".join(words)


def category_order(c):
    m = re.search(r"\d+", c["name"])
    return (0, int(m.group()), c["name"]) if m else (1, 0, c["name"])


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
    for g in groups.values():
        g["categories"].sort(key=category_order)
    return list(groups.values())


# ---------- TSF ----------

def collect_tsf(today):
    soup = get(TSF + "takvim")
    out = []
    for row in soup.select("a.event-row[href*='/etkinlik/']"):
        eid = re.search(r"/etkinlik/(\d+)", row["href"]).group(1)
        h3, p = row.find("h3"), row.find("p")
        if not h3 or not p:
            continue
        name = h3.get_text(" ", strip=True)
        if "sezon" in name.lower():
            continue
        when, _, place = p.get_text(" ", strip=True).partition("·")
        place = place.strip()
        dates = tr_dates(when)
        if not dates or dates[-1] < today:
            continue
        city = find_city(name, place)
        intl = bool(re.search(r"avrupa|dünya|uluslararası|balkan|olimpiyat", name, re.I)) or (place and not city)
        url = urljoin(TSF, row["href"])
        t = {
            "id": f"tsf-{eid}",
            "name": name,
            "city": city if not intl else place,
            "start": dates[0].isoformat(),
            "end": dates[-1].isoformat(),
            "type": "uluslararası" if intl else "ulusal",
            "categories": [],
            "prizes": [],
            "regulation": url,
            "source": "tsf",
        }
        if not intl:
            # Türkiye şampiyonası gibi etkinliklerin ayrı organizasyon sitesi olabiliyor
            try:
                for a in get(url).select("a[href^='http']"):
                    if "organizasyon sitesi" in a.get_text(" ", strip=True).lower():
                        t["website"] = a["href"]
                        break
            except Exception as e:
                log(f"  TSF {eid}: hata {e}")
        out.append(t)
        log(f"  + TSF {name} ({dates[0]})")
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


if __name__ == "__main__":
    main()
