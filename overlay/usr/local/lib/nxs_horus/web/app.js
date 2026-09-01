/* HORUS - logica dashboard. Tutto client-side; i dati arrivano dal backend
   locale (proxy Python) su /api/*. La mappa e' Leaflet 2D (l'ambiente WebKit
   della distro gira in software rendering: niente WebGL, quindi niente
   MapLibre GL). Vista nera di default, con selettore per cambiare basemap. */
"use strict";

// Corregge i path delle icone marker vendorizzate (Leaflet le cerca altrove).
L.Icon.Default.prototype.options.imagePath = "vendor/leaflet/images/";

// ---------------------------------------------------------------------------
// Basemap: la NERA e' il default (CARTO dark). Le altre sono nel selettore.
// Le tile richiedono rete: se offline la mappa resta scura ma i pannelli e i
// feed che rispondono continuano a funzionare.
// ---------------------------------------------------------------------------
// Basemap TUTTE keyless: Esri (arcgisonline) e OSM. NIENTE CARTO: le sue tile
// ora richiedono una API key e mostrano un watermark sulla mappa.
const esriAttr = "Tiles &copy; Esri";
const bases = {
  // noWrap: mondo SINGOLO (le tile non si ripetono). Cosi' gli overlay (cavi,
  // navi, ecc.) non "appaiono e scompaiono" quando ci si sposta lateralmente.
  "Nera (default)": L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    { attribution: esriAttr + " - Dark Gray Canvas", maxZoom: 16, noWrap: true }),
  "Satellite": L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { attribution: esriAttr + ", Maxar, Earthstar Geographics", maxZoom: 19, noWrap: true }),
  "Strade": L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "&copy; OpenStreetMap", maxZoom: 19, noWrap: true }),
  "Chiara": L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    { attribution: esriAttr + " - Light Gray Canvas", maxZoom: 16, noWrap: true }),
};

const map = L.map("map", {
  center: [25, 10],
  zoom: 3,
  minZoom: 2,
  // Canvas: migliaia di marker (telecamere, navi, voli) restano fluidi anche
  // in software rendering (l'ambiente WebKit della distro non ha WebGL).
  preferCanvas: true,
  worldCopyJump: false,
  // Mondo singolo: si resta dentro i confini del planisfero, niente copie vuote.
  maxBounds: [[-85, -180], [85, 180]],
  maxBoundsViscosity: 1.0,
  layers: [bases["Nera (default)"]],
  zoomControl: false,   // lo rimettiamo (in alto a sx c'e' il toggle)
  attributionControl: true,
});
L.control.zoom({ position: "topright" }).addTo(map);
L.control.layers(bases, null, { position: "topright" }).addTo(map);

// ---------------------------------------------------------------------------
// Definizione feed globali. `render` disegna la risposta del backend.
// Ogni feed ha il suo colore e un layer dedicato (toggle indipendente).
// ---------------------------------------------------------------------------
function dot(color, r) {
  return { radius: r || 5, color: color, weight: 1, fillColor: color,
           fillOpacity: 0.6 };
}

// --- Helper per fumetti ricchi ---
function esc(s) {
  const d = document.createElement("div");
  d.textContent = (s === null || s === undefined) ? "" : String(s);
  return d.innerHTML;
}
function popup(title, rows, links) {
  let h = '<div class="pop"><b>' + esc(title) + "</b>";
  const body = rows.filter(r => r[1] !== undefined && r[1] !== null && r[1] !== "");
  if (body.length) {
    h += "<table>";
    body.forEach(r => { h += "<tr><td>" + esc(r[0]) + "</td><td>" + r[1] + "</td></tr>"; });
    h += "</table>";
  }
  (links || []).forEach(l => {
    if (l[1]) h += '<a href="' + esc(l[1]) + '" target="_blank" rel="noopener">' + esc(l[0]) + "</a> ";
  });
  return h + "</div>";
}
function when(ms) { try { return new Date(ms).toLocaleString(); } catch (e) { return ""; } }

const FEEDS = [
  {
    id: "quakes", nome: "Terremoti (24h)", color: "#ff5a8a",
    desc: "USGS - sismi mondiali ultime 24h",
    render(data, layer) {
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        const p = f.properties, m = p.mag || 0;
        const rows = [
          ["Luogo", esc(p.place)],
          ["Magnitudo", esc(m + (p.magType ? " (" + p.magType + ")" : ""))],
          ["Profondità", c[2] != null ? c[2].toFixed(1) + " km" : ""],
          ["Quando", esc(when(p.time))],
          ["Sentito da", p.felt != null ? p.felt + " persone" : ""],
          ["Allerta", esc(p.alert || "")],
          ["Tsunami", p.tsunami ? "sì" : ""],
          ["Significatività", esc(p.sig)],
          ["Rete", esc((p.net || "").toUpperCase())],
        ];
        L.circleMarker([c[1], c[0]], dot("#ff5a8a", Math.max(3, m * 2.2)))
          .bindPopup(popup("M " + m + " - " + (p.place || ""), rows,
            [["Dettagli USGS", p.url]]), { maxWidth: 300 })
          .addTo(layer);
        n++;
      });
      return n;
    },
  },
  {
    id: "volcano", nome: "Vulcani attivi", color: "#ff8c42",
    desc: "Smithsonian GVP - vulcani con eruzione recente",
    render(data, layer) {
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        const p = f.properties;
        const rows = [
          ["Tipo", esc(p.type)],
          ["Ultima eruzione", esc(p.last)],
          ["Paese", esc(p.country)],
          ["Regione", esc(p.region)],
          ["Quota", p.elevation !== "" ? esc(p.elevation) + " m" : ""],
          ["Roccia", esc(p.rock)],
        ];
        let extra = "";
        if (p.photo) extra += '<img class="cam" src="' + esc(p.photo) + '" alt="">';
        if (p.summary) extra += '<div class="summary">' + esc(p.summary) + "</div>";
        const html = popup(p.name || "Vulcano", rows, [["Scheda GVP", p.link]])
          .replace("</div>", extra + "</div>");
        L.circleMarker([c[1], c[0]], dot("#ff8c42", 6))
          .bindPopup(html, { maxWidth: 320 }).addTo(layer);
        n++;
      });
      return n;
    },
  },
  {
    id: "flights", nome: "Voli in tempo reale", color: "#00e5ff",
    desc: "OpenSky - aerei ADS-B (campione mondiale)",
    render(data, layer) {
      let n = 0;
      (data.states || []).forEach(s => {
        const lon = s[5], lat = s[6]; if (lat == null || lon == null) return;
        const alt = s[13] != null ? s[13] : s[7];
        const rows = [
          ["Paese", esc(s[2])],
          ["Quota", alt != null ? Math.round(alt) + " m" : ""],
          ["Velocità", s[9] != null ? Math.round(s[9] * 3.6) + " km/h" : ""],
          ["Rotta", s[10] != null ? Math.round(s[10]) + "°" : ""],
          ["Salita/discesa", s[11] != null ? (s[11] > 0 ? "+" : "") + s[11].toFixed(1) + " m/s" : ""],
          ["A terra", s[8] ? "sì" : "no"],
          ["Squawk", esc(s[14] || "")],
          ["ICAO24", esc(s[0])],
        ];
        L.circleMarker([lat, lon], dot("#00e5ff", 3))
          .bindPopup(popup("Volo " + ((s[1] || "").trim() || "?"), rows,
            [["Traccia su OpenSky",
              s[0] ? "https://opensky-network.org/aircraft-profile?icao24=" + s[0] : ""]]),
            { maxWidth: 300 })
          .addTo(layer);
        n++;
      });
      return n;
    },
  },
  {
    id: "cables", nome: "Cavi sottomarini", color: "#23d18b",
    desc: "TeleGeography - dorsali dati oceaniche",
    render(data, layer) {
      const gj = L.geoJSON(data, {
        style: { color: "#23d18b", weight: 1, opacity: 0.7 },
        onEachFeature: (f, l) => {
          const p = f.properties || {};
          if (p.name) l.bindPopup(popup(p.name, [["ID", esc(p.id)]]), { maxWidth: 280 });
        },
      });
      gj.addTo(layer);
      return (data.features || []).length;
    },
  },
  {
    id: "iss", nome: "Stazione ISS", color: "#a06bff",
    desc: "Posizione attuale della ISS",
    render(data, layer) {
      if (data.latitude == null) return 0;
      const rows = [
        ["Latitudine", data.latitude.toFixed(3)],
        ["Longitudine", data.longitude.toFixed(3)],
        ["Quota", data.altitude != null ? data.altitude.toFixed(0) + " km" : ""],
        ["Velocità", data.velocity != null ? Math.round(data.velocity) + " km/h" : ""],
        ["Visibilità", esc(data.visibility)],
        ["Ora", data.timestamp ? when(data.timestamp * 1000) : ""],
      ];
      // Nel fumetto agganciamo il video in diretta (stream ufficiali YouTube).
      const html = popup("Stazione Spaziale Internazionale", rows).replace(
        "</div>", '<a href="#" class="live-open">&#9654; Video in diretta</a></div>');
      L.circleMarker([data.latitude, data.longitude], dot("#a06bff", 8))
        .bindPopup(html, { maxWidth: 300 })
        .addTo(layer);
      return 1;
    },
  },
  {
    id: "fires", nome: "Incendi mondiali", color: "#ffb000",
    desc: "NASA EONET - incendi attivi (eventi aperti)",
    render(data, layer) {
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        const p = f.properties;
        const rows = [["Aggiornato", esc(p.date && when(p.date))],
          ["Lat, Lon", c[1].toFixed(2) + ", " + c[0].toFixed(2)]];
        L.circleMarker([c[1], c[0]], dot("#ffb000", 3))
          .bindPopup(popup(p.name || "Incendio", rows,
            [["Fonte", p.source], ["EONET", p.link]]), { maxWidth: 300 })
          .addTo(layer);
        n++;
      });
      return n;
    },
  },
  {
    id: "cameras", nome: "Telecamere del traffico", color: "#ff5ac8",
    desc: "Reti ufficiali nel mondo: UK, USA, Canada, Finlandia, NZ (keyless)",
    render(data, layer) {
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        const p = f.properties;
        let html = '<div class="pop cam-pop"><b>' + esc(p.title || "Telecamera") + "</b>";
        html += '<div class="cam-net"><span class="live"></span>' +
          esc(p.network || "") + (p.view ? " · " + esc(p.view) : "") + "</div>";
        if (p.video)
          html += '<video class="cam cam-vid" data-src="' + esc(p.video) +
            '" muted loop playsinline preload="none" poster="' + esc(p.image) + '"></video>';
        else if (p.image)
          html += '<img class="cam cam-live" data-src="' + esc(p.image) + '" alt="">';
        if (p.url && p.url !== p.image && p.url !== p.video)
          html += '<a href="' + esc(p.url) + '" target="_blank" rel="noopener">Apri la scheda</a>';
        html += "</div>";
        L.circleMarker([c[1], c[0]], dot("#ff5ac8", 4))
          .bindPopup(html, { maxWidth: 300 }).addTo(layer);
        n++;
      });
      return n;
    },
  },
  {
    id: "ships", nome: "Navi (AIS)", color: "#5b8cff",
    desc: "AIS mondiale in streaming (aisstream): zooma per popolare un'area",
    render(data, layer) {
      const NAV = { 0: "in navigazione", 1: "alla fonda", 2: "non governabile",
        3: "manovra limitata", 4: "limitata dal pescaggio", 5: "ormeggiata",
        6: "incagliata", 7: "in pesca", 8: "a vela" };
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        const p = f.properties, mmsi = p.mmsi;
        const rows = [
          ["Nome", esc(p.name || "")],
          ["MMSI", esc(mmsi)],
          ["IMO", esc(p.imo || "")],
          ["Call sign", esc(p.callSign || "")],
          ["Destinazione", esc(p.destination || "")],
          ["Velocità", p.sog != null ? p.sog + " nodi" : ""],
          ["Rotta", p.cog != null ? Math.round(p.cog) + "°" : ""],
          ["Prua", p.heading != null && p.heading !== 511 ? p.heading + "°" : ""],
          ["Stato", esc(NAV[p.navStat] || "")],
        ];
        const titolo = p.name ? p.name : ("Nave " + (mmsi || ""));
        L.circleMarker([c[1], c[0]], dot("#5b8cff", 4))
          .bindPopup(popup(titolo, rows,
            [["Scheda MarineTraffic",
              mmsi ? "https://www.marinetraffic.com/en/ais/details/ships/mmsi:" + mmsi : ""]]),
            { maxWidth: 280 })
          .addTo(layer);
        n++;
      });
      return n;
    },
  },
  {
    // I satelliti sono calcolati NEL BROWSER (satellite.js) dai TLE di CelesTrak
    // serviti dal proxy: vedi startSats()/drawSats(). Qui la voce serve solo per
    // l'elenco, il colore e la legenda; il disegno lo fa drawSats().
    id: "satellites", nome: "Satelliti", color: "#e0b3ff",
    desc: "CelesTrak - orbite calcolate live (stazioni, GPS, meteo, GEO...)",
    render() { return 0; },
  },
];

// ---------------------------------------------------------------------------
// UI feed
// ---------------------------------------------------------------------------
const listEl = document.getElementById("feed-list");
const layers = {};   // id -> L.layerGroup
const active = {};    // id -> bool

FEEDS.forEach(fd => {
  layers[fd.id] = L.layerGroup();
  const li = document.createElement("li");
  li.className = "feed";
  li.dataset.id = fd.id;
  li.innerHTML =
    '<span class="sw"></span>' +
    '<span class="swatch" style="background:' + fd.color + '"></span>' +
    '<span class="meta"><span class="nm">' + fd.nome + '</span>' +
    '<span class="ds">' + fd.desc + '</span></span>' +
    '<span class="cnt"></span>';
  li.addEventListener("click", () => toggleFeed(fd.id));
  listEl.appendChild(li);
});

function feedEl(id) { return listEl.querySelector('.feed[data-id="' + id + '"]'); }

function toggleFeed(id) {
  active[id] = !active[id];
  const el = feedEl(id);
  el.classList.toggle("on", active[id]);
  if (active[id]) { map.addLayer(layers[id]); startFeed(id); }
  else { map.removeLayer(layers[id]); stopFeed(id); }
  updateLegend();
  saveActive();
}
// Dispatch: i satelliti girano con un motore proprio (calcolo client), gli
// altri col motore di streaming generico.
function startFeed(id) { if (id === "satellites") startSats(); else startLayer(id); }
function stopFeed(id) { if (id === "satellites") stopSats(); else stopLayer(id); }

// Ricorda quali layer sono accesi, cosi' restano attivi dopo un refresh.
function saveActive() {
  try {
    localStorage.setItem("horus-feeds",
      JSON.stringify(Object.keys(active).filter(id => active[id])));
  } catch (e) { /* storage non disponibile */ }
}
function restoreActive() {
  let ids = [];
  try { ids = JSON.parse(localStorage.getItem("horus-feeds") || "[]"); } catch (e) { ids = []; }
  ids.forEach(id => {
    if (!FEEDS.find(f => f.id === id) || active[id]) return;
    active[id] = true;
    feedEl(id).classList.add("on");
    map.addLayer(layers[id]);
    startFeed(id);
  });
  updateLegend();
}

// ---------------------------------------------------------------------------
// Legenda (key) in basso a sinistra: elenca i feed ATTIVI con il loro colore.
// ---------------------------------------------------------------------------
const legend = L.control({ position: "bottomleft" });
legend.onAdd = function () {
  this._div = L.DomUtil.create("div", "horus-legend");
  this._div.innerHTML = legendHTML();
  return this._div;
};
legend.addTo(map);
function legendHTML() {
  const on = FEEDS.filter(f => active[f.id]);
  let h = "<h4>Legenda</h4>";
  if (!on.length) return h + '<div class="empty">nessun feed attivo</div>';
  on.forEach(f => {
    h += '<div class="row"><span class="box" style="background:' + f.color +
         '"></span>' + f.nome + "</div>";
  });
  return h;
}
function updateLegend() { if (legend._div) legend._div.innerHTML = legendHTML(); }

function feedMsg(text) {
  const el = document.getElementById("feed-msg");
  if (text) { el.textContent = text; el.hidden = false; }
  else { el.textContent = ""; el.hidden = true; }
}

// ---------------------------------------------------------------------------
// MOTORE DI STREAMING: ogni layer viene tenuto in costante aggiornamento e la
// sua ultima risposta e' MEMORIZZATA in IndexedDB; la mappa viene disegnata
// LEGGENDO da IndexedDB. Vantaggi: aggiornamento continuo, resilienza offline
// (all'apertura si rivede subito l'ultimo stato salvato), affidabilita'.
//   live=true  -> oggetti in movimento (navi/aerei/ISS): cadenza dallo slider.
//   live=false -> dati lenti (terremoti/vulcani/incendi/cavi/telecamere):
//                 cadenza propria (lunga), ma sempre ri-verificati.
//   bbox=true  -> si passa il riquadro visibile (navi: popola l'area guardata).
// ---------------------------------------------------------------------------
const STREAM = {
  // navi: sottoscrizione MONDIALE permanente (niente riquadro: col riquadro la
  // vista globale mostrerebbe solo una frazione). Lo store lato server accumula
  // di continuo -> il mondo si riempie sempre di piu'.
  ships:   { live: true,  interval: 5 },
  flights: { live: true,  interval: 10 },
  iss:     { live: true,  interval: 5 },
  quakes:  { live: false, interval: 120 },
  volcano: { live: false, interval: 3600 },
  fires:   { live: false, interval: 900 },
  cables:  { live: false, interval: 86400 },
  cameras: { live: false, interval: 300 },
};
const dueAt = {};      // id -> timestamp(ms) del prossimo poll
const polling = {};    // id -> in corso (evita sovrapposizioni)

function cadence(id) {
  const cfg = STREAM[id] || { interval: 60 };
  return (cfg.live ? parseInt(autoInt.value, 10) : cfg.interval) * 1000;
}

// --- IndexedDB: una cache per feed (chiave = id feed), con timestamp. ---
let hdb = null;
function openDB() {
  return new Promise(res => {
    try {
      const rq = indexedDB.open("horus", 2);
      rq.onupgradeneeded = ev => {
        const db = rq.result;
        if (!db.objectStoreNames.contains("feeds")) db.createObjectStore("feeds", { keyPath: "id" });
        // v2: storico delle scie (solo entita' seguite + ISS). "tracks" tiene i
        // campioni; l'indice composto [layer,key,t] li restituisce ordinati nel
        // tempo. "trackmeta" ha una riga per entita' (conteggio + estremi) per
        // popolare l'elenco dello scrubber senza scorrere tutti i punti.
        if (ev.oldVersion < 2) {
          const tr = db.createObjectStore("tracks", { keyPath: "id", autoIncrement: true });
          tr.createIndex("entt", ["layer", "key", "t"], { unique: false });
          db.createObjectStore("trackmeta", { keyPath: ["layer", "key"] });
        }
      };
      rq.onsuccess = () => res(rq.result);
      rq.onerror = () => res(null);
    } catch (e) { res(null); }
  });
}

// --- Storico scie (IndexedDB) ------------------------------------------------
// Ritenzione configurabile dall'interfaccia (ore); 0 = illimitata (solo il
// tetto sui punti). La scelta resta in localStorage di questo browser.
let TRACK_MAX_AGE_MS = 72 * 3600 * 1000;     // default 72 ore
const TRACK_MAX_POINTS = 4000;               // per entita'
try {
  const h = parseInt(localStorage.getItem("horus.track.hours"), 10);
  if (h > 0) TRACK_MAX_AGE_MS = h * 3600000;
  else if (h === 0) TRACK_MAX_AGE_MS = Infinity;
} catch (e) { /* localStorage assente */ }
function trackRetentionHours() {
  return TRACK_MAX_AGE_MS === Infinity ? 0 : Math.round(TRACK_MAX_AGE_MS / 3600000);
}
// Modalita' di registrazione: "local" (IndexedDB, solo a finestra aperta) o
// "server" (recorder di background su SQLite). Preferenza per-macchina.
function trackMode() {
  try { return localStorage.getItem("horus.track.mode") === "server" ? "server" : "local"; }
  catch (e) { return "local"; }
}
function setTrackMode(m) {
  try { localStorage.setItem("horus.track.mode", m === "server" ? "server" : "local"); } catch (e) {}
}
function setTrackRetentionHours(h) {
  TRACK_MAX_AGE_MS = (h > 0) ? h * 3600000 : Infinity;
  try { localStorage.setItem("horus.track.hours", String(h)); } catch (e) {}
}

// Esporta TUTTO lo storico in un oggetto serializzabile (per il backup).
function trackExportAll() {
  return new Promise(res => {
    if (!hdb) return res(null);
    try {
      const rq = hdb.transaction("tracks", "readonly").objectStore("tracks").getAll();
      rq.onsuccess = () => res({ format: "horus-tracks", version: 1, exported: Date.now(),
        samples: (rq.result || []).map(r => ({ layer: r.layer, key: r.key,
          lat: r.lat, lon: r.lon, t: r.t, name: r.name })) });
      rq.onerror = () => res(null);
    } catch (e) { res(null); }
  });
}

// Importa (fonde) una lista di campioni nel DB vivo. Ritorna quanti inseriti.
async function trackImportMerge(samples) {
  let n = 0;
  const seen = {};
  for (const s of (samples || [])) {
    if (s.lat == null || s.lon == null) continue;
    await trackPut({ layer: s.layer, key: s.key, lat: s.lat, lon: s.lon,
      t: s.t || Date.now(), name: s.name || "" });
    seen[s.layer + "|" + s.key] = true; n++;
  }
  Object.keys(seen).forEach(k => { const p = k.split("|"); trackPrune(p[0], p[1]); });
  return n;
}

// Aggiunge un campione {layer,key,lat,lon,t,name} e aggiorna i metadati.
function trackPut(s) {
  return new Promise(res => {
    if (!hdb || s.lat == null || s.lon == null) return res();
    try {
      const tx = hdb.transaction(["tracks", "trackmeta"], "readwrite");
      const t = s.t || Date.now();
      tx.objectStore("tracks").add({ layer: s.layer, key: String(s.key),
        lat: s.lat, lon: s.lon, t: t, name: s.name || "" });
      const mstore = tx.objectStore("trackmeta"), mk = [s.layer, String(s.key)];
      const gr = mstore.get(mk);
      gr.onsuccess = () => {
        const m = gr.result || { layer: s.layer, key: String(s.key),
          name: s.name || "", first: t, last: t, count: 0 };
        m.count += 1; m.last = Math.max(m.last, t); m.first = Math.min(m.first, t);
        if (s.name) m.name = s.name;
        mstore.put(m);
      };
      tx.oncomplete = () => res(); tx.onerror = () => res();
    } catch (e) { res(); }
  });
}

// Ritorna i campioni di un'entita' tra fromT e toT, ordinati nel tempo.
function trackRange(layer, key, fromT, toT) {
  return new Promise(res => {
    if (!hdb) return res([]);
    try {
      const idx = hdb.transaction("tracks", "readonly").objectStore("tracks").index("entt");
      const lo = [layer, String(key), fromT || 0];
      const hi = [layer, String(key), (toT == null ? 8.64e15 : toT)];
      const rq = idx.getAll(IDBKeyRange.bound(lo, hi));
      rq.onsuccess = () => res(rq.result || []);
      rq.onerror = () => res([]);
    } catch (e) { res([]); }
  });
}

// Elenco delle entita' con storico (dalle righe di trackmeta).
function trackEntities() {
  return new Promise(res => {
    if (!hdb) return res([]);
    try {
      const rq = hdb.transaction("trackmeta", "readonly").objectStore("trackmeta").getAll();
      rq.onsuccess = () => res(rq.result || []);
      rq.onerror = () => res([]);
    } catch (e) { res([]); }
  });
}

// Pota i campioni oltre l'eta' massima o il numero massimo per entita'.
function trackPrune(layer, key) {
  return new Promise(res => {
    if (!hdb) return res();
    try {
      const tx = hdb.transaction(["tracks", "trackmeta"], "readwrite");
      const idx = tx.objectStore("tracks").index("entt");
      const minT = Date.now() - TRACK_MAX_AGE_MS;
      const all = idx.getAll(IDBKeyRange.bound([layer, String(key), 0],
        [layer, String(key), 8.64e15]));
      all.onsuccess = () => {
        const rows = all.result || [];
        const drop = rows.filter(r => r.t < minT);
        const keep = rows.filter(r => r.t >= minT);
        if (keep.length > TRACK_MAX_POINTS)
          drop.push(...keep.slice(0, keep.length - TRACK_MAX_POINTS));
        const store = tx.objectStore("tracks");
        drop.forEach(r => store.delete(r.id));
        const remain = rows.length - drop.length;
        const mstore = tx.objectStore("trackmeta");
        if (remain <= 0) mstore.delete([layer, String(key)]);
        else {
          const kept = rows.filter(r => drop.indexOf(r) < 0);
          const mg = mstore.get([layer, String(key)]);
          mg.onsuccess = () => { const m = mg.result; if (m) {
            m.count = kept.length; m.first = kept[0].t; m.last = kept[kept.length - 1].t;
            mstore.put(m); } };
        }
      };
      tx.oncomplete = () => res(); tx.onerror = () => res();
    } catch (e) { res(); }
  });
}
function dbGet(id) {
  return new Promise(res => {
    if (!hdb) return res(null);
    try {
      const rq = hdb.transaction("feeds", "readonly").objectStore("feeds").get(id);
      rq.onsuccess = () => res(rq.result || null);
      rq.onerror = () => res(null);
    } catch (e) { res(null); }
  });
}
function dbPut(id, data) {
  return new Promise(res => {
    if (!hdb) return res();
    try {
      const tx = hdb.transaction("feeds", "readwrite");
      tx.objectStore("feeds").put({ id: id, data: data, ts: Date.now() });
      tx.oncomplete = () => res(); tx.onerror = () => res();
    } catch (e) { res(); }
  });
}

function renderFromData(id, data) {
  const fd = FEEDS.find(f => f.id === id);
  const cnt = feedEl(id).querySelector(".cnt");
  layers[id].clearLayers();
  const n = fd.render(data, layers[id]);
  cnt.textContent = n; cnt.classList.remove("err"); cnt.title = "";
  return n;
}

// Un giro di aggiornamento: scarica -> salva in IndexedDB -> disegna da lì.
async function pollLayer(id) {
  if (polling[id]) return;
  polling[id] = true;
  const cnt = feedEl(id).querySelector(".cnt");
  try {
    let url = "api/feed/" + id;
    if (STREAM[id] && STREAM[id].bbox) {
      const b = map.getBounds();
      url += "?lamin=" + b.getSouth().toFixed(4) + "&lomin=" + b.getWest().toFixed(4) +
             "&lamax=" + b.getNorth().toFixed(4) + "&lomax=" + b.getEast().toFixed(4);
    }
    const r = await fetch(url);
    const body = await r.json();
    if (!r.ok || body.error) throw new Error(body.error || ("HTTP " + r.status));
    await dbPut(id, body);
    // Se c'e' un fumetto aperto su un layer "live", NON ridisegniamo (lo
    // chiuderemmo sotto il naso): i dati restano aggiornati in IndexedDB e
    // ridisegneremo al giro dopo la chiusura.
    if (!(popupOpen && STREAM[id] && STREAM[id].live)) {
      const rec = await dbGet(id);        // visualizziamo LEGGENDO da IndexedDB
      renderFromData(id, rec ? rec.data : body);
    }
    feedMsg("");
  } catch (e) {
    const rec = await dbGet(id);          // in errore: resta l'ultima cache
    if (rec) renderFromData(id, rec.data);
    cnt.textContent = "!"; cnt.classList.add("err");
    cnt.title = String(e.message || e);
    feedMsg(String(e.message || e));      // motivo leggibile sotto l'elenco
  } finally { polling[id] = false; }
}

// Accende un layer: mostra subito la cache (istantaneo/offline), poi aggiorna.
async function startLayer(id) {
  if (!hdb) hdb = await openDB();
  const cnt = feedEl(id).querySelector(".cnt");
  const rec = await dbGet(id);
  if (rec) renderFromData(id, rec.data); else cnt.textContent = "...";
  pollLayer(id);
  dueAt[id] = Date.now() + cadence(id);
}
function stopLayer(id) { delete dueAt[id]; }   // ferma lo scheduling (cache resta)

// Alias storico: un singolo aggiornamento immediato.
function loadFeed(id) { return pollLayer(id); }

// ---------------------------------------------------------------------------
// SATELLITI: TLE da CelesTrak (via proxy), posizioni calcolate NEL BROWSER con
// satellite.js e ridisegnate di continuo (movimento fluido). Nessun WebGL.
// ---------------------------------------------------------------------------
const GROUP_IT = {
  stations: "Stazioni", "gps-ops": "GPS", galileo: "Galileo",
  "glo-ops": "GLONASS", beidou: "BeiDou", weather: "Meteo", noaa: "NOAA",
  goes: "GOES", science: "Scienza", geo: "Geostazionari",
};
let satRecs = [];        // {name, group, satrec}
let satTLEts = 0;        // quando abbiamo preso i TLE (ms)
let satLoading = false;

async function loadTLE() {
  if (satLoading) return;
  satLoading = true;
  const cnt = feedEl("satellites").querySelector(".cnt");
  cnt.textContent = "..."; cnt.classList.remove("err");
  try {
    const d = await (await fetch("api/tle")).json();
    const sats = d.sats || [];
    if (!sats.length) throw new Error(d.error || "nessun TLE disponibile");
    satRecs = [];
    sats.forEach(s => {
      try {
        const rec = satellite.twoline2satrec(s.l1, s.l2);
        if (rec && !rec.error) satRecs.push({ name: s.name, group: s.group, satrec: rec });
      } catch (e) { /* TLE malformato: salta */ }
    });
    satTLEts = Date.now();
    feedMsg("");
  } catch (e) {
    cnt.textContent = "!"; cnt.classList.add("err"); cnt.title = String(e.message || e);
    feedMsg("Satelliti: " + (e.message || e));
  } finally { satLoading = false; }
}

function drawSats() {
  if (!active["satellites"] || !window.satellite || !satRecs.length) return;
  const now = new Date();
  const gmst = satellite.gstime(now);
  const layer = layers["satellites"];
  layer.clearLayers();
  let n = 0;
  for (let i = 0; i < satRecs.length; i++) {
    const s = satRecs[i];
    let pv;
    try { pv = satellite.propagate(s.satrec, now); } catch (e) { continue; }
    const pos = pv && pv.position;
    if (!pos) continue;
    const gd = satellite.eciToGeodetic(pos, gmst);
    const lat = satellite.degreesLat(gd.latitude), lon = satellite.degreesLong(gd.longitude);
    if (!isFinite(lat) || !isFinite(lon)) continue;
    let vel = "";
    if (pv.velocity) {
      const v = pv.velocity;
      vel = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z).toFixed(2) + " km/s";
    }
    const rows = [
      ["Categoria", esc(GROUP_IT[s.group] || s.group)],
      ["Quota", gd.height.toFixed(0) + " km"],
      ["Velocità", vel],
      ["Lat, Lon", lat.toFixed(2) + ", " + lon.toFixed(2)],
    ];
    L.circleMarker([lat, lon], dot("#e0b3ff", 3))
      .bindPopup(popup(s.name || "Satellite", rows,
        [["Scheda N2YO", "https://www.n2yo.com/?s=" + (s.satrec.satnum || "")]]),
        { maxWidth: 260 })
      .addTo(layer);
    n++;
  }
  feedEl("satellites").querySelector(".cnt").textContent = n;
}

async function startSats() {
  if (!window.satellite) { feedMsg("satellite.js non caricato"); return; }
  if (!satRecs.length || Date.now() - satTLEts > 7200000) await loadTLE();
  drawSats();
}
function stopSats() { /* lo scheduler smette di ridisegnare quando inattivo */ }

document.getElementById("feed-refresh").addEventListener("click", () => {
  Object.keys(active).forEach(id => { if (active[id]) { pollLayer(id); dueAt[id] = Date.now() + cadence(id); } });
});

// ---------------------------------------------------------------------------
// Tab
// ---------------------------------------------------------------------------
const phoneFrame = document.getElementById("phone-frame");
document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("is-active"));
    document.querySelectorAll(".panel").forEach(x => x.classList.remove("is-active"));
    t.classList.add("is-active");
    const panel = t.dataset.panel;
    document.getElementById("panel-" + panel).classList.add("is-active");
    // Nel tab Telefono, se PhoneInfoga e' su mostra l'iframe SOPRA la mappa.
    if (panel === "phone") { phonePoll(); }
    else { phoneFrame.hidden = true; }
    // il ticker sta sulla mappa: nel tab Telefono (iframe a tutto campo) lo nascondo
    document.getElementById("ticker").hidden = (panel === "phone");
    // Leaflet va ridimensionato quando torna visibile.
    if (panel !== "phone") setTimeout(() => map.invalidateSize(), 60);
  });
});

// ---------------------------------------------------------------------------
// Recon: elenco tool installati + esecuzione (backend fa la validazione vera).
// ---------------------------------------------------------------------------
const RECON_HINT = {
  domain: "Dominio (es. esempio.com)",
  username: "Username",
  email: "Indirizzo email",
  phone: "Numero telefono (+39...)",
  ip: "Indirizzo IP",
  host: "Host o IP",
};
const toolSel = document.getElementById("recon-tool");
const targetIn = document.getElementById("recon-target");
const reconHint = document.getElementById("recon-hint");
const reconOut = document.getElementById("recon-out");
let RECON_TOOLS = [];

async function loadTools() {
  try {
    const r = await fetch("api/tools");
    RECON_TOOLS = await r.json();
  } catch (e) { RECON_TOOLS = []; }
  toolSel.innerHTML = "";
  if (!RECON_TOOLS.length) {
    const o = document.createElement("option");
    o.textContent = "nessuno strumento installato"; o.disabled = true;
    toolSel.appendChild(o);
    document.getElementById("recon-run").disabled = true;
    return;
  }
  RECON_TOOLS.forEach(t => {
    const o = document.createElement("option");
    // Non disabilitiamo i non-installati: si possono installare da qui.
    o.value = t.id; o.textContent = t.nome + (t.installed ? "" : " - non installato");
    o.dataset.kind = t.kind;
    o.dataset.installed = t.installed ? "1" : "0";
    toolSel.appendChild(o);
  });
  updateSelState();
}
function updateSelState() {
  const opt = toolSel.selectedOptions[0];
  const kind = opt ? opt.dataset.kind : "host";
  const installed = opt ? opt.dataset.installed === "1" : false;
  reconHint.textContent = RECON_HINT[kind] || "Obiettivo";
  targetIn.placeholder = reconHint.textContent;
  // Installato -> Esegui; non installato -> Installa (on-demand dal catalogo).
  document.getElementById("recon-run").hidden = !installed;
  document.getElementById("recon-install").hidden = installed;
}
toolSel.addEventListener("change", updateSelState);

document.getElementById("recon-install").addEventListener("click", async () => {
  const tool = toolSel.value;
  if (!tool) return;
  const btn = document.getElementById("recon-install");
  btn.disabled = true;
  reconOut.textContent = "Installazione di " + tool +
    " in corso... (pip/container possono richiedere qualche minuto)\n";
  try {
    const r = await fetch("api/recon/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool }),
    });
    const body = await r.json();
    reconOut.textContent = body.output || body.error || "(nessun output)";
    if (body.ok) { await loadTools(); }   // ora risulta installato -> Esegui
  } catch (e) {
    reconOut.textContent = "Errore installazione: " + (e.message || e);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("recon-run").addEventListener("click", async () => {
  const tool = toolSel.value;
  const target = targetIn.value.trim();
  if (!tool || !target) { reconOut.textContent = "Inserisci un obiettivo."; return; }
  reconOut.textContent = "Esecuzione in corso...\n";
  const btn = document.getElementById("recon-run");
  btn.disabled = true;
  try {
    const r = await fetch("api/recon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool, target }),
    });
    const body = await r.json();
    reconOut.textContent = body.output || body.error || "(nessun output)";
    if (body.output) addDossier("recon", tool + " " + target, body.output, { target: target });
  } catch (e) {
    reconOut.textContent = "Errore: " + (e.message || e);
  } finally {
    btn.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// Stato (rete/Tor) dal backend
// ---------------------------------------------------------------------------
async function refreshStatus() {
  const dot = document.getElementById("status-dot");
  const txt = document.getElementById("status-txt");
  try {
    const r = await fetch("api/status");
    const s = await r.json();
    dot.className = "dot ok";
    scanVia = s.tor ? "Tor" : "IP diretto";
    txt.textContent = (s.online ? "in rete" : "offline") +
      (s.tor ? " - via Tor" : "");
    document.getElementById("net-note").textContent = s.tor
      ? "Tor attivo: le query escono dal circuito Tor."
      : "Tor non attivo: le query escono dal tuo IP reale.";
  } catch (e) {
    dot.className = "dot err";
    txt.textContent = "backend non raggiungibile";
  }
}

// ---------------------------------------------------------------------------
// Telefono: PhoneInfoga avviato on-demand e mostrato in iframe su :5000.
// ---------------------------------------------------------------------------
let phoneTimer = null;
async function phoneStatus() {
  try { const r = await fetch("api/phone/status"); return await r.json(); }
  catch (e) { return { up: false }; }
}
async function phonePoll() {
  const s = await phoneStatus();
  const stateEl = document.getElementById("phone-state");
  const openEl = document.getElementById("phone-open");
  if (s.up) {
    stateEl.textContent = "PhoneInfoga attivo su http://127.0.0.1:5000";
    openEl.hidden = false;
    if (!phoneFrame.getAttribute("src")) phoneFrame.src = "http://127.0.0.1:5000";
    phoneFrame.hidden = false;
    if (phoneTimer) { clearInterval(phoneTimer); phoneTimer = null; }
  } else {
    phoneFrame.hidden = true;
    document.getElementById("phone-open").hidden = true;
  }
}
document.getElementById("phone-start").addEventListener("click", async () => {
  const stateEl = document.getElementById("phone-state");
  stateEl.textContent = "Avvio in corso...";
  try {
    const r = await fetch("api/phone/start", { method: "POST" });
    const body = await r.json();
    if (body.error) { stateEl.textContent = body.error; return; }
    if (body.up) { phonePoll(); return; }
    stateEl.textContent = "Avvio del servizio (al primo avvio scarica il container)...";
    let tries = 0;
    if (phoneTimer) clearInterval(phoneTimer);
    phoneTimer = setInterval(async () => {
      tries++;
      const s = await phoneStatus();
      if (s.up) { phonePoll(); }
      else if (tries > 45) {
        clearInterval(phoneTimer); phoneTimer = null;
        stateEl.textContent = "PhoneInfoga non risponde ancora su :5000. "
          + "Riprova, o aprila in una scheda separata.";
      }
    }, 2000);
  } catch (e) { stateEl.textContent = "Errore: " + (e.message || e); }
});

// ---------------------------------------------------------------------------
// Apri/chiudi la barra laterale. SOLO col bottone: nessun automatismo.
// ---------------------------------------------------------------------------
const appEl = document.getElementById("app");
const sideToggle = document.getElementById("side-toggle");
sideToggle.addEventListener("click", () => {
  const collapsed = appEl.classList.toggle("side-collapsed");
  sideToggle.textContent = collapsed ? "☰" : "‹";  // hamburger / <
  sideToggle.title = collapsed ? "Mostra il pannello" : "Nascondi il pannello";
  setTimeout(() => map.invalidateSize(), 60);
});

// ---------------------------------------------------------------------------
// Telecamere: mentre il fumetto e' aperto, rinfresca l'immagine (in diretta).
// Le reti pubbliche servono un JPEG che si rinnova di continuo: aggiungiamo un
// cache-buster ogni pochi secondi cosi' l'immagine si aggiorna sotto gli occhi.
// ---------------------------------------------------------------------------
let camTimer = null;
let popupOpen = false;   // vero mentre un fumetto e' aperto: sospende i ridisegni live
map.on("popupopen", e => {
  popupOpen = true;
  const el = e.popup.getElement();
  if (!el) return;
  // Clip video (TfL): la avviamo appena il fumetto si apre.
  const vid = el.querySelector("video.cam-vid");
  if (vid && !vid.src) {
    vid.src = vid.getAttribute("data-src");
    vid.play().catch(() => {});
  }
  // Immagine fissa (Caltrans/Ontario): la rinfreschiamo mentre e' aperta.
  const img = el.querySelector("img.cam-live");
  if (!img) return;
  const base = img.getAttribute("data-src");
  const bust = () => { img.src = base + (base.indexOf("?") < 0 ? "?" : "&") + "t=" + Date.now(); };
  bust();
  if (camTimer) clearInterval(camTimer);
  camTimer = setInterval(bust, 6000);
});
map.on("popupclose", () => {
  popupOpen = false;
  if (camTimer) { clearInterval(camTimer); camTimer = null; }
});

// ---------------------------------------------------------------------------
// Lightbox: clic su un'immagine .cam (telecamera o foto vulcano) -> ingrandimento.
// ---------------------------------------------------------------------------
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
function openLightbox(src) { lightboxImg.src = src; lightbox.hidden = false; }
function closeLightbox() { lightbox.hidden = true; lightboxImg.removeAttribute("src"); }
document.addEventListener("click", e => {
  const img = e.target.closest("img.cam");
  if (img && img.src) { openLightbox(img.src); }
});
lightbox.addEventListener("click", e => {
  if (e.target === lightbox || e.target.id === "lightbox-close") closeLightbox();
});
document.addEventListener("keydown", e => { if (e.key === "Escape") closeLightbox(); });

// ---------------------------------------------------------------------------
// Aggiornamento in tempo reale: l'interruttore master accende/spegne il flusso
// continuo, lo slider fissa la cadenza dei layer "live" (navi/aerei/ISS). Gli
// altri layer si ri-verificano al loro intervallo. Ogni giro passa dal motore
// (poll -> IndexedDB -> disegno). Il contatore mostra il prossimo aggiornamento.
// ---------------------------------------------------------------------------
const autoOn = document.getElementById("auto-on");
const autoInt = document.getElementById("auto-int");
const autoCount = document.getElementById("auto-count");
let areaDue = 0;

function paintAuto() {
  if (!autoOn.checked) { autoCount.textContent = "in pausa"; return; }
  const now = Date.now();
  let next = Infinity;
  Object.keys(active).forEach(id => {
    if (active[id] && STREAM[id] && STREAM[id].live && dueAt[id] != null)
      next = Math.min(next, dueAt[id] - now);
  });
  autoCount.textContent = (next === Infinity)
    ? "in ascolto" : ("prossimo tra " + Math.max(0, Math.ceil(next / 1000)) + "s");
}
autoInt.addEventListener("change", () => {
  const now = Date.now();
  Object.keys(active).forEach(id => { if (active[id] && STREAM[id] && STREAM[id].live) dueAt[id] = now; });
  paintAuto();
});
autoOn.addEventListener("change", () => {
  const now = Date.now();
  if (autoOn.checked) Object.keys(active).forEach(id => { if (active[id]) dueAt[id] = now; });
  paintAuto();
});
setInterval(() => {
  if (!autoOn.checked) { paintAuto(); return; }
  const now = Date.now();
  Object.keys(active).forEach(id => {
    if (!active[id] || id === "satellites") return;   // i satelliti hanno il loro giro
    if (dueAt[id] == null) dueAt[id] = now;
    if (now >= dueAt[id]) { pollLayer(id); dueAt[id] = now + cadence(id); }
  });
  // Satelliti: ricalcolo posizioni ogni secondo (movimento fluido); TLE ogni 2h.
  if (active["satellites"]) {
    if (!satLoading && now - satTLEts > 7200000) loadTLE();
    if (!popupOpen) drawSats();
  }
  if (activeArea && now >= areaDue) {
    areaSearch(activeArea);
    areaDue = now + parseInt(autoInt.value, 10) * 1000;
  }
  paintAuto();
}, 1000);
paintAuto();

// La vista cambia (pan/zoom): i layer col riquadro (navi) riseguono l'area.
let moveDeb = null;
map.on("moveend", () => {
  clearTimeout(moveDeb);
  moveDeb = setTimeout(() => {
    Object.keys(active).forEach(id => {
      if (active[id] && STREAM[id] && STREAM[id].bbox) { pollLayer(id); dueAt[id] = Date.now() + cadence(id); }
    });
  }, 400);
});

// ---------------------------------------------------------------------------
// Dossier d'indagine -> report HTML + JSON nel loot.
// Ogni voce e' arricchita: tipo, titolo, dettaglio, ora (ISO + locale),
// provenienza dello scan (Tor/IP), obiettivo, coordinate e tag quando note.
// I moduli chiamano addDossier(kind, title, detail, extra?) dove extra puo'
// contenere {lat, lon, target, tags}. Retrocompatibile: extra e' opzionale.
// ---------------------------------------------------------------------------
const dossier = [];
function addDossier(kind, title, detail, extra) {
  extra = extra || {};
  const now = new Date();
  const e = {
    type: kind, title: title, detail: detail,
    time: now.toLocaleString(), iso: now.toISOString(),
    via: (typeof scanVia === "string" ? scanVia : "IP diretto"),
  };
  if (extra.target) e.target = extra.target;
  if (typeof extra.lat === "number" && typeof extra.lon === "number" &&
      !isNaN(extra.lat) && !isNaN(extra.lon)) { e.lat = extra.lat; e.lon = extra.lon; }
  if (extra.tags && extra.tags.length) e.tags = extra.tags;
  dossier.push(e);
  renderDossier();
}
const DOSSIER_LABEL = {
  geoint: "GEOINT", recon: "Ricognizione", socmint: "SOCMINT",
  email: "Email", correlazione: "Correlazione", area: "Area",
  exif: "Metadati foto", nota: "Nota",
};
function dossierLabel(t) { return DOSSIER_LABEL[t] || t; }
function renderDossier() {
  const ul = document.getElementById("report-list");
  const stats = document.getElementById("report-stats");
  ul.innerHTML = "";
  if (!dossier.length) {
    ul.innerHTML = '<li class="empty">Ancora nessuna voce. Esegui una recon o un GEOINT.</li>';
    if (stats) stats.innerHTML = "";
    return;
  }
  // Barra statistiche: conteggi per tipo + quante voci hanno coordinate.
  const cnt = {};
  let geo = 0;
  dossier.forEach(e => { cnt[e.type] = (cnt[e.type] || 0) + 1; if (e.lat != null) geo++; });
  if (stats) {
    let s = '<span class="rep-chip rep-chip-tot">' + dossier.length + " voci</span>";
    Object.keys(cnt).forEach(k => {
      s += '<span class="rep-chip">' + esc(dossierLabel(k)) + " " + cnt[k] + "</span>";
    });
    if (geo) s += '<span class="rep-chip rep-chip-geo">&#128205; ' + geo + " su mappa</span>";
    stats.innerHTML = s;
  }
  dossier.forEach((e, i) => {
    const li = document.createElement("li");
    let meta = e.time + " · " + esc(e.via);
    if (e.lat != null) meta += " · &#128205; " + e.lat.toFixed(4) + ", " + e.lon.toFixed(4);
    li.innerHTML = '<div class="rk">' + esc(dossierLabel(e.type)) + "</div><div class='rt'>" +
      esc(e.title) + "</div><div class='rd'>" + meta + "</div>" +
      '<button class="rep-del" data-i="' + i + '" title="Rimuovi questa voce">&times;</button>';
    ul.appendChild(li);
  });
  ul.querySelectorAll(".rep-del").forEach(b => b.addEventListener("click", () => {
    dossier.splice(parseInt(b.dataset.i, 10), 1); renderDossier();
  }));
}
renderDossier();
// Ricorda titolo/analista tra le sessioni.
try {
  const t = localStorage.getItem("horus.report.title");
  const o = localStorage.getItem("horus.report.operator");
  if (t) document.getElementById("report-title").value = t;
  if (o) document.getElementById("report-operator").value = o;
} catch (e) {}
function reportMeta() {
  const title = document.getElementById("report-title").value.trim();
  const operator = document.getElementById("report-operator").value.trim();
  const objective = document.getElementById("report-objective").value.trim();
  try {
    localStorage.setItem("horus.report.title", title);
    localStorage.setItem("horus.report.operator", operator);
  } catch (e) {}
  return { title: title, operator: operator, objective: objective,
           via: (typeof scanVia === "string" ? scanVia : "IP diretto"),
           graph_svg: (typeof window.HORUS_graphSVG === "string" ? window.HORUS_graphSVG : ""),
           entries: dossier };
}
document.getElementById("report-save").addEventListener("click", async () => {
  const note = document.getElementById("report-note");
  if (!dossier.length) { note.textContent = "Il dossier è vuoto."; return; }
  note.textContent = "Salvataggio...";
  try {
    const r = await fetch("api/report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reportMeta()),
    });
    const b = await r.json();
    note.textContent = b.path
      ? ("Salvato: " + b.path + (b.json ? "  +  " + b.json : ""))
      : (b.error || "errore");
  } catch (e) { note.textContent = "Errore: " + (e.message || e); }
});
document.getElementById("report-clear").addEventListener("click", () => {
  dossier.length = 0; renderDossier();
  document.getElementById("report-note").textContent = "";
});

// ---------------------------------------------------------------------------
// GEOINT: geolocalizza IP/dominio + Shodan, e lo mette sulla mappa.
// ---------------------------------------------------------------------------
const geoLayer = L.layerGroup().addTo(map);
document.getElementById("geoint-run").addEventListener("click", async () => {
  const target = document.getElementById("geoint-target").value.trim();
  const out = document.getElementById("geoint-out");
  if (!target) { out.textContent = "Inserisci un IP o un dominio."; return; }
  out.textContent = "Analisi in corso...";
  try {
    const r = await fetch("api/geoint", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: target }),
    });
    const d = await r.json();
    if (d.error) { out.textContent = d.error; return; }
    const luogo = [d.city, d.region, d.country].filter(Boolean).join(", ");
    const lines = [
      "Target : " + target + "  ->  " + d.ip,
      luogo ? "Luogo  : " + luogo : "",
      d.org ? "Org    : " + d.org + (d.asn ? " (" + d.asn + ")" : "") : "",
      (d.ports && d.ports.length) ? "Porte  : " + d.ports.join(", ")
        : "Porte  : nessun dato Shodan",
      (d.vulns && d.vulns.length) ? "CVE    : " + d.vulns.join(", ") : "",
      (d.hostnames && d.hostnames.length) ? "Host   : " + d.hostnames.join(", ") : "",
      (d.tags && d.tags.length) ? "Tag    : " + d.tags.join(", ") : "",
    ].filter(Boolean);
    out.textContent = lines.join("\n");
    if (d.lat != null && d.lon != null) {
      const rows = [
        ["IP", esc(d.ip)], ["Luogo", esc(luogo)],
        ["Org", esc(d.org)], ["ASN", esc(d.asn)],
        ["Porte", esc((d.ports || []).join(", "))],
        ["CVE", esc((d.vulns || []).join(", "))],
        ["Host", esc((d.hostnames || []).join(", "))],
        ["Tag", esc((d.tags || []).join(", "))],
      ];
      const m = L.circleMarker([d.lat, d.lon], dot("#00e5ff", 8))
        .bindPopup(popup("GEOINT: " + target, rows), { maxWidth: 320 });
      geoLayer.addLayer(m);
      map.setView([d.lat, d.lon], 6);
      m.openPopup();
    } else {
      out.textContent += "\n(nessuna geolocalizzazione: " + (d.geo_error || "?") + ")";
    }
    const gx = { target: target };
  if (typeof d.lat === "number" && typeof d.lon === "number") { gx.lat = d.lat; gx.lon = d.lon; }
  if (d.country) gx.tags = [d.country].concat((d.tags || []).slice(0, 4));
  addDossier("geoint", target + " -> " + d.ip, out.textContent, gx);
  } catch (e) { out.textContent = "Errore: " + (e.message || e); }
});

// ---------------------------------------------------------------------------
// Ricerca per area: disegna un riquadro -> voli e terremoti in quell'area.
// ---------------------------------------------------------------------------
const areaLayer = L.layerGroup().addTo(map);
let drawing = false, drawStart = null, rubber = null, activeArea = null;
const areaNote = document.getElementById("area-note");
document.getElementById("area-draw").addEventListener("click", () => {
  drawing = true;
  areaNote.textContent = "Trascina sulla mappa per disegnare l'area.";
  map.dragging.disable();
  map.getContainer().style.cursor = "crosshair";
});
map.on("mousedown", e => {
  if (!drawing) return;
  drawStart = e.latlng;
  rubber = L.rectangle([drawStart, drawStart],
    { color: "#00e5ff", weight: 1, dashArray: "4", fillOpacity: 0.05 }).addTo(map);
});
map.on("mousemove", e => {
  if (drawing && drawStart && rubber) rubber.setBounds(L.latLngBounds(drawStart, e.latlng));
});
map.on("mouseup", async e => {
  if (!drawing || !drawStart) return;
  const b = L.latLngBounds(drawStart, e.latlng);
  drawing = false; drawStart = null;
  map.dragging.enable();
  map.getContainer().style.cursor = "";
  if (rubber) { map.removeLayer(rubber); rubber = null; }
  await areaSearch(b);
});
async function areaSearch(b) {
  activeArea = b;   // memorizzata per l'auto-aggiornamento
  areaNote.textContent = "Interrogazione area...";
  areaLayer.clearLayers();
  L.rectangle(b, { color: "#00e5ff", weight: 1, fill: false }).addTo(areaLayer);
  const q = "lamin=" + b.getSouth() + "&lomin=" + b.getWest() +
            "&lamax=" + b.getNorth() + "&lomax=" + b.getEast();
  try {
    const r = await fetch("api/area?" + q);
    const d = await r.json();
    let nf = 0, nq = 0;
    (((d.flights || {}).states) || []).forEach(s => {
      const lon = s[5], lat = s[6]; if (lat == null || lon == null) return;
      L.circleMarker([lat, lon], dot("#00e5ff", 3))
        .bindPopup(popup("Volo " + ((s[1] || "").trim() || "?"),
          [["Paese", esc(s[2])], ["Quota", s[13] != null ? Math.round(s[13]) + " m" : ""]]))
        .addTo(areaLayer); nf++;
    });
    (((d.quakes || {}).features) || []).forEach(f => {
      const c = f.geometry.coordinates;
      L.circleMarker([c[1], c[0]], dot("#ff5a8a", 5))
        .bindPopup(popup("M " + f.properties.mag, [["Luogo", esc(f.properties.place)]]))
        .addTo(areaLayer); nq++;
    });
    areaNote.textContent = "Area: " + nf + " voli, " + nq + " terremoti (24h).";
    const bc = b.getCenter();
    addDossier("area", "Ricerca area", areaNote.textContent + "\nbbox " + q,
               { lat: bc.lat, lon: bc.lng });
  } catch (e) { areaNote.textContent = "Errore area: " + (e.message || e); }
}

// ---------------------------------------------------------------------------
// Ticker news: banda che scorre in basso con gli ultimi titoli mondiali (GDELT).
// ---------------------------------------------------------------------------
const tickerTrack = document.getElementById("ticker-track");
let newsQuery = "";                       // "" = notizie mondiali aggregate
async function loadNews(query) {
  if (typeof query === "string") newsQuery = query.trim();
  const clearBtn = document.getElementById("ticker-q-clear");
  if (clearBtn) clearBtn.hidden = !newsQuery;
  const url = newsQuery ? ("api/news?q=" + encodeURIComponent(newsQuery)) : "api/news";
  try {
    tickerTrack.textContent = newsQuery ? ("  Ricerca 360°: " + newsQuery + " …") : "  …";
    const r = await fetch(url);
    const d = await r.json();
    const arts = (d.articles || []).filter(a => a.title);
    if (!arts.length) {
      tickerTrack.textContent = newsQuery
        ? ("  Nessun risultato per “" + newsQuery + "”.")
        : "  Nessuna notizia al momento.";
      return;
    }
    // Contenuto DUPLICATO: con l'animazione a -50% il loop e' senza stacco.
    const pre = newsQuery
      ? '<span class="news-scope">360°: ' + esc(newsQuery) + '</span><span class="sep">•</span>' : "";
    const build = () => arts.map(a =>
      '<a class="news-item" href="' + esc(a.url) + '" data-title="' + esc(a.title) +
      '" data-src="' + esc(a.domain) + '">' + esc(a.title) +
      ' <span class="dom">(' + esc(a.domain) + ')</span></a>' +
      '<span class="sep">•</span>').join("");
    tickerTrack.innerHTML = pre + build() + pre + build();
    // velocita' proporzionale alla lunghezza (piu' titoli = piu' lento)
    tickerTrack.style.animationDuration = Math.max(40, arts.length * 4) + "s";
  } catch (e) {
    tickerTrack.textContent = "  News non disponibili (rete/GDELT non raggiungibili).";
  }
}
document.getElementById("ticker-label").addEventListener("click", () => {
  document.getElementById("ticker").classList.toggle("min");
});
(function () {
  const q = document.getElementById("ticker-q");
  const clr = document.getElementById("ticker-q-clear");
  if (q) q.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); loadNews(q.value); }
  });
  if (clr) clr.addEventListener("click", () => { if (q) q.value = ""; loadNews(""); });
})();

// Lettore news IN-WINDOW: clic su un titolo -> apre l'articolo nella stessa
// finestra (iframe). Se il sito vieta l'incorporamento, ripiego elegante.
const reader = document.getElementById("reader");
const readerContent = document.getElementById("reader-content");
const readerBlock = document.getElementById("reader-block");
// Stato dell'articolo aperto: tiene originale E traduzione, per commutare.
let readerState = null;
function newsAutoTr() { try { return localStorage.getItem("horus.news.autotranslate") === "1"; } catch (e) { return false; } }
function setNewsAutoTr(on) { try { localStorage.setItem("horus.news.autotranslate", on ? "1" : "0"); } catch (e) {} }

async function openReader(url, title, src) {
  document.getElementById("reader-src").textContent = src || "";
  document.getElementById("reader-ext").href = url;
  readerContent.hidden = false; readerBlock.hidden = true;
  readerContent.innerHTML = '<p class="reader-loading">Carico l\'articolo...</p>';
  reader.classList.remove("expanded");   // riparte piccola in basso a destra
  reader.hidden = false;
  readerState = null;
  updateTrButton();
  try {
    // Modalita' lettura: estraiamo il testo lato server (funziona anche coi
    // siti che vietano l'iframe).
    const d = await (await fetch("api/read?url=" + encodeURIComponent(url))).json();
    const paras = d.paragraphs || [];
    if (!paras.length) {
      readerContent.hidden = true; readerBlock.hidden = false;
      document.getElementById("reader-block-link").href = d.url || url;
      return;
    }
    readerState = {
      url: d.url || url, src: src, date: d.date, image: d.image,
      origTitle: d.title || title || "", origParas: paras,
      trTitle: null, trParas: null, translated: false,
    };
    renderReader();
    // "Traduci sempre": se attivo, traduce subito dopo il caricamento.
    if (newsAutoTr()) translateReader(true);
  } catch (e) {
    readerContent.hidden = true; readerBlock.hidden = false;
    document.getElementById("reader-block-link").href = url;
  }
}

// Disegna l'articolo nella lingua corrente (originale o tradotta).
function renderReader() {
  if (!readerState) return;
  const st = readerState, tr = st.translated;
  const title = tr && st.trTitle != null ? st.trTitle : st.origTitle;
  const paras = tr && st.trParas ? st.trParas : st.origParas;
  document.getElementById("reader-title").textContent = title;
  let h = "<h1>" + esc(title) + "</h1>";
  const meta = [st.src, st.date, tr ? "tradotto" : null].filter(Boolean).join(" · ");
  if (meta) h += '<div class="reader-by">' + esc(meta) + "</div>";
  if (st.image) h += '<img class="reader-lead" src="' + esc(st.image) + '" alt="">';
  h += paras.map(t => "<p>" + esc(t) + "</p>").join("");
  h += '<a class="reader-orig" href="' + esc(st.url) +
    '" target="_blank" rel="noopener">Leggi l\'originale &#8599;</a>';
  readerContent.innerHTML = h;
  readerContent.scrollTop = 0;
  updateTrButton();
}

function updateTrButton() {
  const b = document.getElementById("reader-translate");
  if (!b) return;
  b.hidden = !readerState;
  b.textContent = (readerState && readerState.translated) ? "↩ Originale" : "🌐 Traduci";
}

// Traduce (o commuta) l'articolo. auto=true = chiamata automatica (nessun toggle
// all'indietro): traduce e mostra la versione italiana.
async function translateReader(auto) {
  if (!readerState) return;
  const st = readerState;
  if (!auto && st.translated) { st.translated = false; renderReader(); return; }
  if (st.trParas) { st.translated = true; renderReader(); return; }  // gia' tradotto: riusa
  const b = document.getElementById("reader-translate");
  if (b) { b.textContent = "traduco…"; b.disabled = true; }
  try {
    const q = [st.origTitle].concat(st.origParas);
    const d = await (await fetch("api/translate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: q, tl: "it" }),
    })).json();
    const t = d.t || [];
    if (t.length) {
      st.trTitle = t[0];
      st.trParas = t.slice(1);
      st.translated = true;
    }
  } catch (e) { /* fallisce: resta l'originale */ }
  if (b) b.disabled = false;
  renderReader();
}

function closeReader() { reader.hidden = true; readerContent.innerHTML = ""; readerState = null; }
document.getElementById("reader-close").addEventListener("click", closeReader);
document.getElementById("reader-expand").addEventListener("click", () => {
  reader.classList.toggle("expanded");
});
document.getElementById("reader-translate").addEventListener("click", () => translateReader(false));
(function () {
  const auto = document.getElementById("reader-tr-auto");
  if (!auto) return;
  auto.checked = newsAutoTr();
  auto.addEventListener("change", () => {
    setNewsAutoTr(auto.checked);
    // se lo attivo mentre leggo l'originale, traduco subito
    if (auto.checked && readerState && !readerState.translated) translateReader(true);
  });
})();
// --- Diretta ISS: streaming video live (canali YouTube ufficiali, no chiavi) --
// Usiamo l'embed "live_stream" per canale (l'ID canale e' piu' stabile del video,
// che cambia a ogni diretta). Se un canale non e' in onda, l'utente ne sceglie un
// altro o apre su YouTube col link in alto a destra.
const LIVE_STREAMS = [
  { name: "NASA - ISS ufficiale (Terra dallo spazio)", ch: "UCLA_DiR1FfKNvjuUpBHmylQ" },
  { name: "ISS Live Now - Terra dalla ISS (24/7)", ch: "UCUYAa03TMH88eOGh37howNQ" },
  { name: "Space Videos - Terra dalla ISS (24/7)", ch: "UCMYjvyMEMmeYWYya_qagAxQ" },
  { name: "ESA - European Space Agency", ch: "UCIBaDdAbGlFDeS33shmlD0A" },
];
const liveEl = document.getElementById("live");
const liveFrame = document.getElementById("live-frame");
const liveSel = document.getElementById("live-src");
const liveMsgEl = document.getElementById("live-msg");
LIVE_STREAMS.forEach((s, i) => {
  const o = document.createElement("option");
  o.value = i; o.textContent = s.name; liveSel.appendChild(o);
});
function showLiveMsg(html, color) {
  liveMsgEl.style.color = color || "var(--text)";
  liveMsgEl.innerHTML = html; liveMsgEl.hidden = false;
}
// Player YouTube via IFrame API: forza il play DENTRO la finestra. L'autoplay
// via solo URL viene spesso bloccato dal browser (resta il poster fermo);
// playVideo() da API parte anche senza click, purche' muto. Lo script e'
// esterno ma la diretta richiede comunque Internet.
let ytPlayer = null, ytReady = false, ytPending = null;
window.onYouTubeIframeAPIReady = function () {
  ytReady = true;
  if (ytPending) { const v = ytPending; ytPending = null; playLiveVideo(v); }
};
function loadYTApi() {
  if (ytReady || document.getElementById("yt-api")) return;
  const t = document.createElement("script");
  t.id = "yt-api"; t.src = "https://www.youtube.com/iframe_api";
  document.head.appendChild(t);
}
function playLiveVideo(vid) {
  liveMsgEl.hidden = true;   // mostra il player, nasconde l'overlay
  const url = "https://www.youtube.com/embed/" + vid +
    "?enablejsapi=1&autoplay=1&mute=1&playsinline=1&rel=0";
  if (ytReady && window.YT && window.YT.Player) {
    if (ytPlayer && ytPlayer.loadVideoById) {
      ytPlayer.loadVideoById(vid);
      try { ytPlayer.mute(); ytPlayer.playVideo(); } catch (e) { /* ignora */ }
    } else {
      liveFrame.src = url;
      ytPlayer = new YT.Player("live-frame", {
        events: { onReady: e => {
          try { e.target.mute(); e.target.playVideo(); } catch (x) { /* ignora */ }
        } },
      });
    }
  } else {                     // API non ancora pronta: autoplay via URL + attesa
    liveFrame.src = url; ytPending = vid; loadYTApi();
  }
}
async function setLiveStream(i) {
  const s = LIVE_STREAMS[i] || LIVE_STREAMS[0];
  document.getElementById("live-ext").href =
    "https://www.youtube.com/channel/" + s.ch + "/live";
  if (!(ytPlayer && ytPlayer.loadVideoById)) showLiveMsg("Cerco la diretta&hellip;", "#88ffaa");
  try {
    // Il videoId della diretta cambia ogni volta: lo risolve il server dalla
    // pagina /live del canale (l'embed per-canale e' deprecato da YouTube).
    const d = await (await fetch("api/live?ch=" + encodeURIComponent(s.ch))).json();
    if (d.videoId) { playLiveVideo(d.videoId); }
    else {
      if (ytPlayer && ytPlayer.stopVideo) { try { ytPlayer.stopVideo(); } catch (e) {} }
      showLiveMsg("Nessuna diretta in corso su questo canale. Prova un altra " +
        "sorgente oppure apri su YouTube col link in alto a destra.", "#c8f5ff");
    }
  } catch (e) {
    showLiveMsg("Errore nel recupero della diretta.", "#ff5a8a");
  }
}
function openLive() {
  liveEl.classList.remove("expanded");
  liveEl.hidden = false;
  liveSel.value = "0";
  loadYTApi();          // precarica l'API cosi' e' pronta al primo play
  setLiveStream(0);
}
function closeLive() {
  liveEl.hidden = true;
  if (ytPlayer && ytPlayer.stopVideo) { try { ytPlayer.stopVideo(); } catch (e) {} }
  else { liveFrame.src = "about:blank"; }
}
liveSel.addEventListener("change", () => setLiveStream(+liveSel.value));
document.getElementById("live-close").addEventListener("click", closeLive);
document.getElementById("live-expand").addEventListener("click",
  () => liveEl.classList.toggle("expanded"));

document.addEventListener("click", e => {
  const lv = e.target.closest("a.live-open");
  if (lv) { e.preventDefault(); openLive(); return; }
  const a = e.target.closest("a.news-item");
  if (a) { e.preventDefault(); openReader(a.getAttribute("href"), a.dataset.title, a.dataset.src); }
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { closeReader(); closeLive(); }
});

loadNews();
setInterval(loadNews, 300000);  // ogni 5 minuti

// ---------------------------------------------------------------------------
// Impostazioni: chiavi personali dell'utente (restano su questo computer).
// ---------------------------------------------------------------------------
const settingsEl = document.getElementById("settings");
async function openSettings() {
  settingsEl.hidden = false;
  document.getElementById("settings-note").textContent = "";
  document.getElementById("set-ais").value = "";
  document.getElementById("set-aisprem").value = "";
  try {
    const s = await (await fetch("api/settings")).json();
    document.getElementById("set-ais").placeholder =
      s.aisstream ? "già impostata (lascia vuoto per tenerla)" : "incolla la chiave";
    document.getElementById("set-aisprem").placeholder =
      s.ais_premium ? "già impostata (lascia vuoto per tenerla)" : "incolla la chiave (facoltativa)";
    document.getElementById("set-feeds").value = s.news_feeds || "";
  } catch (e) { /* offline: campi vuoti */ }
  // Catalogo fonti news: checkbox RAGGRUPPATE per zona mondiale
  try {
    const d = await (await fetch("api/news-sources")).json();
    const box = document.getElementById("news-src-list");
    box.innerHTML = "";
    const byReg = {};
    (d.sources || []).forEach(s => { (byReg[s.region] = byReg[s.region] || []).push(s); });
    Object.keys(byReg).forEach(reg => {
      const h = document.createElement("div");
      h.className = "src-region"; h.textContent = reg;
      box.appendChild(h);
      byReg[reg].forEach(src => {
        const lab = document.createElement("label");
        lab.className = "src-item";
        lab.title = src.name;
        lab.innerHTML = '<input type="checkbox" value="' + esc(src.id) + '"' +
          (src.on ? " checked" : "") + '><span>' + esc(src.name) + "</span>";
        box.appendChild(lab);
      });
    });
  } catch (e) { /* offline */ }
  // Stato registrazione storico (background su SQLite vs client)
  await loadTrackSettings();
}

async function loadTrackSettings() {
  const modeSel = document.getElementById("set-track-mode");
  const hoursSel = document.getElementById("set-track-hours");
  const bg = document.getElementById("set-track-bg");
  const note = document.getElementById("set-track-status");
  if (!modeSel) return;
  let st = null;
  try { st = await (await fetch("api/recorder")).json(); } catch (e) {}
  // La modalita' effettiva: se il recorder e' attivo lato server -> "server".
  const mode = (st && st.enabled) ? "server" : trackMode();
  setTrackMode(mode);
  modeSel.value = mode;
  bg.hidden = (mode !== "server");
  if (st) {
    if (hoursSel) hoursSel.value = String(st.hours != null ? st.hours : 72);
    if (note) note.textContent = trackStatusText(st);
  }
}
function trackStatusText(st) {
  if (!st.enabled) return "Registrazione in background spenta.";
  return (st.running ? "Attivo" : "Avvio in corso") + " · " + st.samples +
    " campioni, " + st.entities + " entità, " + st.follows.length + " seguite.";
}
async function saveRecorder(enabled) {
  const hoursSel = document.getElementById("set-track-hours");
  const note = document.getElementById("set-track-status");
  const body = { enabled: enabled };
  if (hoursSel) body.hours = parseInt(hoursSel.value, 10);
  try {
    const st = await (await fetch("api/recorder", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })).json();
    if (note) note.textContent = trackStatusText(st);
    return st;
  } catch (e) { if (note) note.textContent = "Errore: " + (e.message || e); }
}
document.getElementById("set-track-mode").addEventListener("change", async e => {
  const m = e.target.value;
  setTrackMode(m);
  document.getElementById("set-track-bg").hidden = (m !== "server");
  await saveRecorder(m === "server");
});
document.getElementById("set-track-hours").addEventListener("change", () => {
  if (trackMode() === "server") saveRecorder(true);
  setTrackRetentionHours(parseInt(document.getElementById("set-track-hours").value, 10) || 0);
});

function closeSettings() { settingsEl.hidden = true; }
document.getElementById("settings-open").addEventListener("click", openSettings);
document.getElementById("settings-close").addEventListener("click", closeSettings);
document.getElementById("settings-save").addEventListener("click", async () => {
  const note = document.getElementById("settings-note");
  note.textContent = "Salvataggio...";
  const body = { news_feeds: document.getElementById("set-feeds").value };
  const a = document.getElementById("set-ais").value.trim();
  const ap = document.getElementById("set-aisprem").value.trim();
  if (a) body.aisstream_key = a;
  if (ap) body.ais_premium_key = ap;
  // Fonti news selezionate (id spuntati)
  body.news_sources = Array.from(
    document.querySelectorAll("#news-src-list input:checked")).map(c => c.value);
  try {
    const d = await (await fetch("api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })).json();
    note.textContent = d.ok ? "Salvato. Ricarico i feed interessati."
      : (d.error || "errore");
    ["cameras", "ships"].forEach(id => { if (active[id]) loadFeed(id); });
    loadNews();
  } catch (e) { note.textContent = "Errore: " + (e.message || e); }
});
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSettings(); });

// ---------------------------------------------------------------------------
// Finestre flottanti trascinabili (lettore news, video, Centro Correlazioni).
// Si trascinano dall'header; la posizione e' ricordata per finestra. Quando la
// finestra e' espansa (quasi a schermo intero) il drag e' disattivato e le
// regole CSS .expanded riprendono il controllo.
// ---------------------------------------------------------------------------
function makeDraggable(winId, handleId) {
  const win = document.getElementById(winId);
  const handle = document.getElementById(handleId);
  if (!win || !handle) return;
  const KEY = "horus.win." + winId;
  let lastPos = null, dragging = false, sx, sy, ox, oy;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  function applyPos(left, top) {
    const w = win.offsetWidth || 200;
    left = clamp(left, 4, Math.max(4, window.innerWidth - Math.min(w, 140) - 4));
    top = clamp(top, 4, Math.max(4, window.innerHeight - 34));
    win.style.left = left + "px"; win.style.top = top + "px";
    win.style.right = "auto"; win.style.bottom = "auto";
    lastPos = { left: left, top: top };
  }
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null");
    if (s && typeof s.left === "number") { lastPos = s; if (!win.classList.contains("expanded")) applyPos(s.left, s.top); }
  } catch (e) {}
  handle.style.cursor = "move";
  handle.style.touchAction = "none";
  handle.addEventListener("pointerdown", (ev) => {
    if (win.classList.contains("expanded")) return;
    if (ev.target.closest("button, input, select, textarea, a, label")) return;
    const r = win.getBoundingClientRect();
    ox = r.left; oy = r.top; sx = ev.clientX; sy = ev.clientY; dragging = true;
    try { handle.setPointerCapture(ev.pointerId); } catch (e) {}
    handle.style.cursor = "grabbing"; ev.preventDefault();
  });
  handle.addEventListener("pointermove", (ev) => {
    if (dragging) applyPos(ox + (ev.clientX - sx), oy + (ev.clientY - sy));
  });
  function end(ev) {
    if (!dragging) return;
    dragging = false; handle.style.cursor = "move";
    try { handle.releasePointerCapture(ev.pointerId); } catch (e) {}
    if (lastPos) { try { localStorage.setItem(KEY, JSON.stringify(lastPos)); } catch (e) {} }
  }
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", end);
  // Quando si espande, lascia il layout al CSS; quando si ricomprime, torna
  // alla posizione trascinata.
  new MutationObserver(() => {
    if (win.classList.contains("expanded")) {
      win.style.left = win.style.top = win.style.right = win.style.bottom = "";
    } else if (lastPos) { applyPos(lastPos.left, lastPos.top); }
  }).observe(win, { attributes: true, attributeFilter: ["class"] });
}
makeDraggable("reader", "reader-head");
makeDraggable("live", "live-head");
makeDraggable("correlate", "corr-head");

// Avvio
loadTools();
refreshStatus();
restoreActive();   // riattiva i layer che erano accesi (persistono al refresh)
