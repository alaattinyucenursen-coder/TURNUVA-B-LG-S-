const $ = (id) => document.getElementById(id);
let all = [];
let quick = "all";

const DAY = 86400000;
const MONTHS = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split(" ");
const TYPE_LABELS = { il: "İl turnuvası", ulusal: "Ulusal", "uluslararası": "Uluslararası" };

const parse = (iso) => new Date(iso + "T00:00:00");
const todayIso = () => new Date().toISOString().slice(0, 10);
const daysUntil = (iso) => Math.round((parse(iso) - parse(todayIso())) / DAY);
const lower = (s) => (s || "").toLocaleLowerCase("tr");

// Toplanan veriler dış sitelerden geldiği için sayfaya basmadan önce kaçışlanır
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Seçilen il ve yaş bir sonraki açılışta hatırlanır
const store = {
  get(k) { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};

function dateRange(t) {
  const s = parse(t.start), e = parse(t.end || t.start);
  if (t.start === (t.end || t.start)) return `${s.getDate()} ${MONTHS[s.getMonth()]}`;
  if (s.getMonth() === e.getMonth()) return `${s.getDate()}–${e.getDate()} ${MONTHS[s.getMonth()]}`;
  return `${s.getDate()} ${MONTHS[s.getMonth()]} – ${e.getDate()} ${MONTHS[e.getMonth()]}`;
}

function status(t) {
  const d = daysUntil(t.start);
  if (d < 0) return '<span class="tag live">Devam ediyor</span>';
  if (d === 0) return '<span class="tag live">Bugün başlıyor</span>';
  if (d === 1) return '<span class="tag soon">Yarın</span>';
  if (d <= 7) return `<span class="tag soon">${d} gün kaldı</span>`;
  return "";
}

const link = (href, text, cls = "btn light") =>
  href ? `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener">${text}</a>` : "";

function card(t) {
  const s = parse(t.start);
  const cats = t.categories.length
    ? t.categories.map((c) => link(c.url, esc(c.name), "chip")).join("")
    : '<span class="muted">Kategoriler henüz açıklanmadı</span>';
  const prizes = t.prizes.length
    ? `<ul>${t.prizes.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`
    : '<span class="muted">Ödüller henüz açıklanmadı</span>';
  const meta = [t.city, t.timeControl, t.rounds && `${t.rounds} tur`].filter(Boolean).map(esc).join(" · ");

  return `<details>
    <summary>
      <div class="day"><b>${s.getDate()}</b><span>${MONTHS[s.getMonth()].slice(0, 3)}</span></div>
      <div class="head">
        <h2>${esc(t.name)}</h2>
        <div class="meta">${esc(dateRange(t))}${meta ? " · " + meta : ""}</div>
        <div class="tags">${status(t)}<span class="tag">${TYPE_LABELS[t.type] || esc(t.type)}</span>${t.prizes.length ? '<span class="tag">🏆 Ödüllü</span>' : ""}</div>
      </div>
    </summary>
    <div class="more">
      <h3>Kategoriler <span class="muted">· eşleşme ve sonuçlar için dokun</span></h3>
      <div>${cats}</div>
      <h3>Ödüller</h3>${prizes}
      <div class="actions">
        ${link(t.regulation, "📄 Yönerge")}${link(t.registration, "✍️ Kayıt ol", "btn")}${link(t.website, "🌐 Turnuva sitesi")}
      </div>
    </div>
  </details>`;
}

function matchesAge(t, age) {
  if (!age) return true;
  const re = age === "açık" ? /açık/ : new RegExp(`(^|\\D)0?${age}(\\D|$)`);
  return t.categories.some((c) => re.test(lower(c.name)));
}

function matchesQuick(t) {
  const d = daysUntil(t.start);
  switch (quick) {
    case "week": return d <= 7;
    case "month": return d <= 31;
    case "prize": return t.prizes.length > 0;
    case "all": return true;
    default: return t.type === quick;
  }
}

function render() {
  const q = lower($("q").value.trim());
  const city = $("city").value;
  const age = $("age").value;
  const rows = all.filter((t) =>
    (!q || lower(t.name).includes(q) || lower(t.city).includes(q)) &&
    (!city || t.city === city) && matchesAge(t, age) && matchesQuick(t));

  $("count").textContent = all.length ? `${rows.length} turnuva` : "";
  if (!rows.length) {
    $("list").innerHTML = '<div class="empty">Bu seçimlere uyan turnuva yok.<br>Filtreleri değiştirmeyi dene.</div>';
    return;
  }
  // Turnuvaları aylara göre grupla
  let html = "", lastMonth = "";
  for (const t of rows) {
    const s = parse(t.start);
    const m = daysUntil(t.start) < 0 ? "Devam edenler" : `${MONTHS[s.getMonth()]} ${s.getFullYear()}`;
    if (m !== lastMonth) { html += `<div class="month">${m}</div>`; lastMonth = m; }
    html += card(t);
  }
  $("list").innerHTML = html;
}

// Mobil uygulamada liste her açılışta siteden indirilir; internet yoksa uygulamadaki kopya kullanılır.
const native = window.Capacitor?.isNativePlatform?.();
const LIST_URL = native ? "https://alaattinyucenursen-coder.github.io/TURNUVA-B-LG-S-/tournaments.json" : "tournaments.json";

async function fetchList() {
  try {
    const res = await fetch(LIST_URL, { cache: "no-store" });
    if (res.ok) return { data: await res.json(), offline: false };
  } catch (e) {}
  return { data: await (await fetch("tournaments.json")).json(), offline: true };
}

async function load() {
  $("refresh").classList.add("spin");
  try {
    const { data, offline } = await fetchList();
    const today = todayIso();
    all = data.tournaments.filter((t) => (t.end || t.start) >= today).sort((a, b) => a.start.localeCompare(b.start));

    const cities = [...new Set(all.map((t) => t.city).filter(Boolean))].sort((a, b) => a.localeCompare(b, "tr"));
    const saved = store.get("il");
    $("city").innerHTML = '<option value="">📍 Tüm iller</option>' +
      cities.map((c) => `<option ${c === saved ? "selected" : ""}>${esc(c)}</option>`).join("");
    $("age").value = store.get("yas");

    $("notice").hidden = !offline;
    $("notice").textContent = offline ? "İnternet bağlantısı yok, son kaydedilen liste gösteriliyor." : "";
    $("updated").textContent = "Son güncelleme: " + new Date(data.updated).toLocaleString("tr-TR", { dateStyle: "long", timeStyle: "short" });
    render();
  } catch (e) {
    $("list").innerHTML = '<div class="empty">Turnuvalar yüklenemedi.<br>Yenile düğmesine dokunarak tekrar dene.</div>';
  } finally {
    $("refresh").classList.remove("spin");
  }
}

$("q").addEventListener("input", render);
$("city").addEventListener("change", () => { store.set("il", $("city").value); render(); });
$("age").addEventListener("change", () => { store.set("yas", $("age").value); render(); });
$("refresh").addEventListener("click", load);
$("quick").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  quick = b.dataset.f;
  for (const x of $("quick").children) x.classList.toggle("on", x === b);
  render();
});

// Uygulamada dış bağlantılar uygulama içi tarayıcıda açılır; geri tuşu uygulamaya döner
if (native) {
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href^='http']");
    const Browser = window.Capacitor.Plugins.Browser;
    if (a && Browser) {
      e.preventDefault();
      Browser.open({ url: a.href, toolbarColor: "#1f2937" });
    }
  });
  // Yeni ve yaklaşan turnuva bildirimleri için izin iste (Android 13+ ve iOS)
  window.Capacitor.Plugins.BackgroundRunner?.requestPermissions({ apis: ["notifications"] }).catch(() => {});
}

load();
