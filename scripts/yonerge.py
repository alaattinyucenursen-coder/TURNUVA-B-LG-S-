"""İl temsilciliği sitelerinden turnuva yönergesini bulur ve ödül bölümünü çıkarır.

Yol: chess-results'taki "Official Homepage of the Organizer" bağlantısı -> il sitesi ->
turnuvanın chess-results bağlantısını içeren duyuru -> duyurudaki PDF -> "ÖDÜL" bölümü.
"""

import re
from urllib.parse import urljoin

import pymupdf

MAX_PDF_BYTES = 8_000_000
PRIZE_WORDS = re.compile(r"kupa|madalya|ödül|plaket|sertifika|belge|tl\b|₺|nakit|hediye|derece|birinci|ikinci|üçüncü|\d\.\s*(?:ye|ya|e|a)\b", re.I)
GOOD_PDF = re.compile(r"y[öo]?nerge|ynerge|talimat", re.I)
BAD_PDF = re.compile(r"liste|kay[ıi]?t|kayt|sonu[çc]|e[şs]le[şs]me|s[ıi]ralama|fide|kural|hakem|g[öo]revlendirme", re.I)
# Ödül bölümünde geçen ama ödülü anlatmayan genel kurallar
GENERIC = re.compile(r"tören|hak iddia|tamamını alır|birden fazla|paylaştırıl|devredil", re.I)
STOP_WORDS = {"SATRANÇ", "TURNUVASI", "2026", "2027", "EKİM", "BAYRAMI"}


def _upper(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


def _is_pdf(href):
    return href.lower().split("?")[0].endswith(".pdf")


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

    def _rank(self, links, base, name):
        """PDF bağlantılarını yönerge olma olasılığına göre sıralar."""
        words = {w for w in re.findall(r"\w{4,}", _upper(name)) if w not in STOP_WORDS}
        scored = []
        for a in links:
            label = a["href"] + " " + a.get_text(" ", strip=True)
            score = 3 * bool(GOOD_PDF.search(label)) - 5 * bool(BAD_PDF.search(label))
            score += sum(w in _upper(label) for w in words)
            scored.append((score, urljoin(base, a["href"])))
        return [u for s, u in sorted(scored, key=lambda x: -x[0]) if s > -3]

    def _candidates_near(self, node, base, name):
        """Bir bağlantının çevresindeki (aynı duyurudaki) PDF'leri ya da duyuru sayfasını bulur."""
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            pdfs = [a for a in node.select("a[href]") if _is_pdf(a["href"])]
            if pdfs:
                return self._rank(pdfs, base, name)
            more = [a for a in node.select("a[href]")
                    if re.search(r"devam|detay|oku", a.get_text(" ", strip=True), re.I)]
            if more:
                return self._pdfs_on(urljoin(base, more[0]["href"]), name)
        return []

    def _pdfs_on(self, url, name):
        if _is_pdf(url):
            return [url]
        page = self._page(url)
        if page is None:
            return []
        return self._rank([a for a in page.select("a[href]") if _is_pdf(a["href"])], url, name)

    def candidates(self, homepage, tnr_ids, name):
        soup = self._page(homepage)
        if soup is None:
            return []
        # 1) Turnuvanın chess-results bağlantısını içeren duyuru
        for a in soup.select("a[href]"):
            m = re.search(r"tnr(\d+)", a["href"], re.I)
            if m and m.group(1) in tnr_ids:
                found = self._candidates_near(a, homepage, name)
                if found:
                    return found
        # 2) Başlığı turnuva adına benzeyen duyuru
        words = {w for w in re.findall(r"\w{4,}", _upper(name)) if w not in STOP_WORDS}
        best, score = None, 0
        for a in soup.select("a[href]"):
            s = sum(w in _upper(a.get_text(" ", strip=True)) for w in words)
            if s > score and s >= max(1, len(words) // 2):
                best, score = urljoin(homepage, a["href"]), s
        return self._pdfs_on(best, name) if best else []

    def prizes(self, homepage, tnr_ids, name):
        cands = self.candidates(homepage, tnr_ids, name)
        if not cands:
            self.log(f"    yönerge bulunamadı ({homepage})")
            return None, []
        first = None
        for pdf in cands[:3]:
            try:
                data = self.fetch_bytes(pdf, MAX_PDF_BYTES)
                with pymupdf.open(stream=data, filetype="pdf") as doc:
                    text = "\n".join(page.get_text() for page in doc)
            except Exception as e:
                self.log(f"    PDF okunamadı {pdf}: {e}")
                continue
            found = extract_prizes(text)
            self.log(f"    yönerge: {pdf} -> {found}")
            if found:
                return pdf, found
            first = first or pdf
        return first, []


def extract_prizes(text):
    """Yönerge metnindeki ödül bölümünü kısa cümleler halinde döndürür."""
    text = re.sub(r"[-]", " ", text)  # PDF'teki özel madde imleri
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    for i, l in enumerate(lines):
        # "Ödül Töreni" gibi program satırlarını atla; ödül anlatan ilk bölümü al
        if re.search(r"ÖDÜL", _upper(l)) and len(l) < 80 and not re.search(r"TÖREN", _upper(l)):
            found = _section(lines, i)
            if found:
                return found
    return []


def _section(lines, start):
    # Başlık satırında ödül bilgisi de olabilir ("ÖDÜLLER: Her kategoride ilk 3...")
    head = re.split(r"ÖDÜL\w*\s*:?", lines[start], maxsplit=1, flags=re.I)[-1].strip()
    section = [head] if head else []
    for l in lines[start + 1:start + 25]:
        # Yeni bir başlığa geldiysek dur ("9- İTİRAZLAR", "KURALLAR:" gibi)
        if re.match(r"^\d{1,2}\s*[-.)]\s*[A-ZÇĞİÖŞÜ /]{4,}:?$", l) or (l.isupper() and l.endswith(":") and not PRIZE_WORDS.search(l)):
            break
        section.append(l)
    # Satır sonları PDF'te rastgele; cümlelere göre yeniden böl
    parts = re.split(r"(?<=[.!])\s+(?=[A-ZÇĞİÖŞÜ0-9])|\s+(?=[-•*]\s)", " ".join(section))
    out = []
    for p in parts:
        p = re.sub(r"^(\d+(\.\d+)*[.)-]?\s+)", "", p.lstrip("-•*; ")).strip()
        p = re.sub(r"^(Temel\s+)?Ödüller\s*:?\s*", "", p, flags=re.I)
        if p and PRIZE_WORDS.search(p) and not GENERIC.search(p):
            out.append(p[:200])
    return out[:8]
