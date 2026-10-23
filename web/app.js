const $ = (id) => document.getElementById(id);
let all = [];

const fmt = (d) =>
  new Date(d + "T00:00:00").toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" });

// Biten turnuvalar listede gösterilmez.
const today = new Date().toISOString().slice(0, 10);
const TYPE_LABELS = { il: "İl", ulusal: "Ulusal", "uluslararası": "Uluslararası" };
const isActive = (t) => (t.end || t.start) >= today;

function card(t) {
  const cats = t.categories.length
    ? t.categories.map((c) => `<a class="chip" href="${c.url}" target="_blank" rel="noopener">${c.name}</a>`).join("")
    : '<span class="muted">Kategoriler henüz açıklanmadı</span>';
  const prizes = t.prizes.length
    ? `<ul>${t.prizes.map((p) => `<li>${p}</li>`).join("")}</ul>`
    : '<span class="muted">Ödüller henüz açıklanmadı</span>';
  const links = [
    t.regulation && `<a href="${t.regulation}" target="_blank" rel="noopener">Yönerge</a>`,
    t.registration && `<a href="${t.registration}" target="_blank" rel="noopener">Kayıt</a>`,
    t.website && `<a href="${t.website}" target="_blank" rel="noopener">Turnuva sitesi</a>`,
  ].filter(Boolean).join(" · ");

  return `<article>
    <div class="top"><span class="badge">${TYPE_LABELS[t.type] || t.type}</span><span class="date">${fmt(t.start)} – ${fmt(t.end)}</span></div>
    <h2>${t.name}</h2>
    <p class="muted">${t.city || "Yer açıklanmadı"}${t.timeControl ? " · " + t.timeControl : ""}${t.rounds ? " · " + t.rounds + " tur" : ""}</p>
    <h3>Kategoriler <small>(eşleşme ve sonuçlar için dokun)</small></h3><div>${cats}</div>
    <h3>Ödüller</h3>${prizes}
    <p class="links">${links}</p>
  </article>`;
}

function render() {
  const q = $("q").value.toLocaleLowerCase("tr");
  const city = $("city").value;
  const type = $("type").value;
  const cat = $("cat").value.toLocaleLowerCase("tr");
  const rows = all.filter((t) =>
    (!q || t.name.toLocaleLowerCase("tr").includes(q)) &&
    (!city || t.city === city) &&
    (!type || t.type === type) &&
    (!cat || t.categories.some((c) => c.name.toLocaleLowerCase("tr").includes(cat)))
  );
  $("list").innerHTML = rows.length ? rows.map(card).join("") : '<p class="muted">Bu filtrelere uyan turnuva yok.</p>';
}

// Mobil uygulamada liste her açılışta siteden indirilir; internet yoksa uygulamadaki kopya kullanılır.
const native = window.Capacitor?.isNativePlatform?.();
const LIST_URL = native ? "https://alaattinyucenursen-coder.github.io/TURNUVA-B-LG-S-/tournaments.json" : "tournaments.json";

async function fetchList() {
  try {
    const res = await fetch(LIST_URL, { cache: "no-store" });
    if (res.ok) return await res.json();
  } catch (e) {}
  return (await fetch("tournaments.json")).json();
}

async function load() {
  // Her açılışta güncel listeyi çeker; yeni turnuvalar eklenir, bitenler düşer.
  const data = await fetchList();
  all = data.tournaments.filter(isActive).sort((a, b) => a.start.localeCompare(b.start));
  const cities = [...new Set(all.map((t) => t.city).filter(Boolean))].sort((a, b) => a.localeCompare(b, "tr"));
  $("city").innerHTML = '<option value="">Tüm iller</option>' + cities.map((c) => `<option>${c}</option>`).join("");
  $("updated").textContent = "Son güncelleme: " + new Date(data.updated).toLocaleString("tr-TR");
  render();
}

["q", "city", "type", "cat"].forEach((id) => $(id).addEventListener("input", render));
load();

// Yeni ve yaklaşan turnuva bildirimleri için izin iste (Android 13+ ve iOS)
if (native) window.Capacitor.Plugins.BackgroundRunner?.requestPermissions({ apis: ["notifications"] }).catch(() => {});
