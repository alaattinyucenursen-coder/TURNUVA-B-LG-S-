"""İl temsilciliği sitelerinden turnuva yönergesini bulur ve ödül bölümünü çıkarır.

Yol: chess-results'taki "Official Homepage of the Organizer" bağlantısı -> il sitesi ->
turnuvanın chess-results bağlantısını içeren duyuru -> duyurudaki PDF -> "ÖDÜL" bölümü.
"""

import io
import re
from urllib.parse import urljoin

from pypdf import PdfReader

MAX_PDF_BYTES = 8_000_000
PRIZE_WORDS = re.compile(r"kupa|madalya|ödül|plaket|sertifika|belge|tl\b|₺|nakit|hediye|derece|birinci|ikinci|üçüncü|\d\.\s*(?:ye|ya|e|a)\b", re.I)


def _upper(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


class YonergeBulucu:
    def __init__(self, get, fetch_bytes, log):
        self.get = get
        self.fetch_bytes = fetch_bytes
        self.log = log
        self.pages = {}

    def _page(self, url):
        if url not in self.pages:
            try:
                self.pages[url] = self.get(url)
            except Exception as e:
                self.log(f"    sayfa açılamadı {url}: {e}")
                self.pages[url] = None
        return self.pages[url]

    def _pdfs_near(self, node, base):
        """Bir bağlantının çevresindeki (aynı duyurudaki) PDF bağlantılarını bulur."""
        for _ in range(6):
            node = node.parent
            if node is None:
                return [], None
            pdfs = [urljoin(base, a["href"]) for a in node.select("a[href]")
                    if a["href"].lower().split("?")[0].endswith(".pdf")]
            if pdfs:
                return pdfs, None
            more = [a for a in node.select("a[href]")
                    if re.search(r"devam|detay|oku", a.get_text(" ", strip=True), re.I)]
            if more:
                return [], urljoin(base, more[0]["href"])
        return [], None

    def find_pdf(self, homepage, tnr_ids, name):
        soup = self._page(homepage)
        if soup is None:
            return None
        # 1) Turnuvanın chess-results bağlantısını içeren duyuru
        for a in soup.select("a[href*='tnr']"):
            m = re.search(r"tnr(\d+)", a["href"])
            if m and m.group(1) in tnr_ids:
                pdfs, article = self._pdfs_near(a, homepage)
                if pdfs:
                    return pdfs[0]
                if article:
                    page = self._page(article)
                    if page:
                        pdfs = [urljoin(article, x["href"]) for x in page.select("a[href]")
                                if x["href"].lower().split("?")[0].endswith(".pdf")]
                        if pdfs:
                            return pdfs[0]
        # 2) Başlığı turnuva adına benzeyen duyuru
        words = {w for w in re.findall(r"\w{4,}", _upper(name)) if w not in {"SATRANÇ", "TURNUVASI", "2026", "2027"}}
        best, score = None, 0
        for a in soup.select("a[href]"):
            text = _upper(a.get_text(" ", strip=True))
            s = sum(w in text for w in words)
            if s > score and len(words) and s >= max(2, len(words) // 2):
                best, score = urljoin(homepage, a["href"]), s
        if best:
            if best.lower().split("?")[0].endswith(".pdf"):
                return best
            page = self._page(best)
            if page:
                for x in page.select("a[href]"):
                    if x["href"].lower().split("?")[0].endswith(".pdf"):
                        return urljoin(best, x["href"])
        return None

    def prizes(self, homepage, tnr_ids, name):
        pdf = self.find_pdf(homepage, tnr_ids, name)
        if not pdf:
            self.log(f"    yönerge bulunamadı ({homepage})")
            return None, []
        try:
            data = self.fetch_bytes(pdf, MAX_PDF_BYTES)
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        except Exception as e:
            self.log(f"    PDF okunamadı {pdf}: {e}")
            return pdf, []
        found = extract_prizes(text)
        self.log(f"    yönerge: {pdf} -> {len(found)} ödül satırı")
        return pdf, found


def extract_prizes(text):
    """Yönerge metnindeki ödül bölümünü kısa satırlar halinde döndürür."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    start = None
    for i, l in enumerate(lines):
        if re.search(r"ÖDÜL", _upper(l)) and len(l) < 80:
            start = i
            break
    if start is None:
        return []
    section = []
    for l in lines[start + 1:start + 25]:
        # Yeni bir başlığa geldiysek dur ("9- İTİRAZLAR", "KURALLAR:" gibi)
        if re.match(r"^\d{1,2}\s*[-.)]\s*[A-ZÇĞİÖŞÜ /]{4,}:?$", l) or (l.isupper() and l.endswith(":") and not PRIZE_WORDS.search(l)):
            break
        section.append(l)
    # Satır sonları PDF'te rastgele; cümlelere göre yeniden böl
    parts = re.split(r"(?<=[.!])\s+(?=[A-ZÇĞİÖŞÜ0-9])|\s+(?=[-•*]\s)", " ".join(section))
    out = [p.lstrip("-•* ").strip()[:200] for p in parts]
    return [p for p in out if PRIZE_WORDS.search(p)][:8]
