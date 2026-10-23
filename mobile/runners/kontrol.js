// Arka planda birkaç saatte bir çalışır: turnuva listesini indirir, yeni eklenen ve
// 3 gün sonra başlayacak turnuvalar için bildirim gösterir.
const LIST_URL = "https://alaattinyucenursen-coder.github.io/TURNUVA-B-LG-S-/tournaments.json";
const REMIND_DAYS = 3;

function kvGet(key, fallback) {
  try {
    const r = CapacitorKV.get(key);
    return r && r.value ? JSON.parse(r.value) : fallback;
  } catch (e) {
    return fallback;
  }
}

// Turnuva kimliğinden sabit bir bildirim numarası üretir
function notificationId(text) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return h;
}

addEventListener("kontrol", async (resolve, reject) => {
  try {
    const res = await fetch(LIST_URL);
    const tournaments = (await res.json()).tournaments;
    const today = new Date().toISOString().slice(0, 10);
    const remindDay = new Date(Date.now() + REMIND_DAYS * 86400000).toISOString().slice(0, 10);

    const seen = kvGet("gorulen", null);
    const reminded = kvGet("hatirlatilan", {});
    const notifications = [];

    // İlk çalışmada mevcut listeyi "yeni" diye bildirmeyelim
    if (seen !== null) {
      const fresh = tournaments.filter((t) => !seen.includes(t.id));
      if (fresh.length === 1) {
        const t = fresh[0];
        notifications.push({ id: notificationId(t.id), title: "Yeni turnuva", body: `${t.name} · ${t.city || ""} ${t.start}` });
      } else if (fresh.length > 1) {
        notifications.push({ id: notificationId("yeni-" + today), title: `${fresh.length} yeni turnuva eklendi`,
          body: fresh.slice(0, 5).map((t) => t.name).join(", ") });
      }
    }

    for (const t of tournaments) {
      if (t.start === remindDay && reminded[t.id] !== t.start) {
        notifications.push({ id: notificationId("hatirlat-" + t.id), title: `${REMIND_DAYS} gün sonra başlıyor`,
          body: `${t.name}${t.city ? " · " + t.city : ""}` });
        reminded[t.id] = t.start;
      }
    }

    if (notifications.length) CapacitorNotifications.schedule(notifications);

    // Biten turnuvaları kayıttan temizle
    const active = new Set(tournaments.map((t) => t.id));
    for (const id of Object.keys(reminded)) if (!active.has(id)) delete reminded[id];
    CapacitorKV.set("gorulen", JSON.stringify(tournaments.map((t) => t.id)));
    CapacitorKV.set("hatirlatilan", JSON.stringify(reminded));
    resolve();
  } catch (err) {
    console.error("Turnuva kontrolü başarısız: " + err);
    reject(err);
  }
});
