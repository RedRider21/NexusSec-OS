/* HORUS - logica dashboard. Tutto client-side; i dati arrivano dal backend
   locale (proxy Python) su /api/*. La mappa e' Leaflet 2D (l'ambiente WebKit
   della distro gira in software rendering: niente WebGL, quindi niente
   MapLibre GL). Vista nera di default, con selettore per cambiare basemap. */
"use strict";

// Corregge i path delle icone marker vendorizzate (Leaflet le cerca altrove).
L.Icon.Default.prototype.options.imagePath = "vendor/leaflet/images/";

// ---------------------------------------------------------------------------
// CACHE TILE OFFLINE (IndexedDB). HORUS gira su una distro spesso OFFLINE: le
// tile viste online vengono salvate e riproposte senza rete. Un precarico dei
// livelli a basso zoom (Impostazioni) rende il MONDO visibile anche offline,
// senza incorporare immagini binarie nella ISO.
// ---------------------------------------------------------------------------
const TILE_DB = "horus-tiles", TILE_STORE = "tiles";
let _tileDbP = null;
function tileDb() {
  if (_tileDbP) return _tileDbP;
  _tileDbP = new Promise((res, rej) => {
    const rq = indexedDB.open(TILE_DB, 1);
    rq.onupgradeneeded = () => {
      const db = rq.result;
      if (!db.objectStoreNames.contains(TILE_STORE)) db.createObjectStore(TILE_STORE);
    };
    rq.onsuccess = () => res(rq.result);
    rq.onerror = () => rej(rq.error);
  }).catch(() => null);
  return _tileDbP;
}
async function tileGet(key) {
  const db = await tileDb(); if (!db) return null;
  return new Promise(res => {
    try {
      const r = db.transaction(TILE_STORE, "readonly").objectStore(TILE_STORE).get(key);
      r.onsuccess = () => res(r.result || null);
      r.onerror = () => res(null);
    } catch (e) { res(null); }
  });
}
async function tilePut(key, blob) {
  const db = await tileDb(); if (!db) return;
  try {
    db.transaction(TILE_STORE, "readwrite").objectStore(TILE_STORE).put(blob, key);
  } catch (e) { /* quota/altro: la cache e' best-effort */ }
}
async function tileClear() {
  const db = await tileDb(); if (!db) return;
  return new Promise(res => {
    try {
      const r = db.transaction(TILE_STORE, "readwrite").objectStore(TILE_STORE).clear();
      r.onsuccess = () => res(true); r.onerror = () => res(false);
    } catch (e) { res(false); }
  });
}
async function tileCount() {
  const db = await tileDb(); if (!db) return 0;
  return new Promise(res => {
    try {
      const r = db.transaction(TILE_STORE, "readonly").objectStore(TILE_STORE).count();
      r.onsuccess = () => res(r.result || 0); r.onerror = () => res(0);
    } catch (e) { res(0); }
  });
}

// TileLayer con cache: prima IndexedDB, poi rete (e salva), infine caricamento
// diretto come ripiego. Gli object URL blob vengono revocati allo scarico tile.
const CachedTileLayer = L.TileLayer.extend({
  createTile(coords, done) {
    const img = document.createElement("img");
    img.setAttribute("role", "presentation"); img.alt = "";
    const url = this.getTileUrl(coords);
    const finish = () => done(null, img);
    tileGet(url).then(blob => {
      if (blob) { img.onload = finish; img.src = URL.createObjectURL(blob); return; }
      fetch(url, { mode: "cors" }).then(r => r.ok ? r.blob() : Promise.reject())
        .then(b => { img.onload = finish; img.src = URL.createObjectURL(b); tilePut(url, b); })
        .catch(() => {                       // offline/CORS: prova diretto
          img.onload = finish; img.onerror = () => done(null, img);
          img.crossOrigin = ""; img.src = url;
        });
    }).catch(() => { img.onload = finish; img.src = url; });
    return img;
  },
  onAdd(m) {
    L.TileLayer.prototype.onAdd.call(this, m);
    this.on("tileunload", e => {
      const s = e.tile && e.tile.src;
      if (s && s.indexOf("blob:") === 0) { try { URL.revokeObjectURL(s); } catch (_) {} }
    });
    return this;
  }
});
function cachedTileLayer(url, opts) { return new CachedTileLayer(url, opts); }

// Precarico del mondo a basso zoom: scarica e salva in IndexedDB i livelli
// z0..zMax (poche centinaia di tile) cosi' offline il planisfero c'e' comunque.
async function primeWorld(layer, zMax, onProgress) {
  const tpl = layer._url, opts = layer.options;
  let total = 0; for (let z = 0; z <= zMax; z++) total += Math.pow(4, z);
  let done = 0, ok = 0;
  for (let z = 0; z <= zMax; z++) {
    const n = Math.pow(2, z);
    for (let x = 0; x < n; x++) for (let y = 0; y < n; y++) {
      const url = L.Util.template(tpl, Object.assign(
        { x, y, z, s: (opts.subdomains && opts.subdomains[0]) || "a" }, opts));
      done++;
      if (!(await tileGet(url))) {
        try {
          const r = await fetch(url, { mode: "cors" });
          if (r.ok) { await tilePut(url, await r.blob()); ok++; }
        } catch (e) { /* salta la tile non raggiungibile */ }
      } else { ok++; }
      if (onProgress && (done % 8 === 0 || done === total)) onProgress(done, total, ok);
    }
  }
  return { total, ok };
}

// ---------------------------------------------------------------------------
// Basemap: la NERA e' il default (Esri dark). Le altre sono nel selettore.
// Con la cache offline: le aree gia' viste (e i livelli precaricati) restano
// visibili senza rete; le zone mai viste offline restano scure.
// ---------------------------------------------------------------------------
// Basemap TUTTE keyless: Esri (arcgisonline) e OSM. NIENTE CARTO: le sue tile
// ora richiedono una API key e mostrano un watermark sulla mappa.
const esriAttr = "Tiles &copy; Esri";
const bases = {
  // noWrap: mondo SINGOLO (le tile non si ripetono). Cosi' gli overlay (cavi,
  // navi, ecc.) non "appaiono e scompaiono" quando ci si sposta lateralmente.
  "Nera (default)": cachedTileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    { attribution: esriAttr + " - Dark Gray Canvas", maxZoom: 16, noWrap: true }),
  "Satellite": cachedTileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { attribution: esriAttr + ", Maxar, Earthstar Geographics", maxZoom: 19, noWrap: true }),
  "Strade": cachedTileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "&copy; OpenStreetMap", maxZoom: 19, noWrap: true, subdomains: "abc" }),
  "Chiara": cachedTileLayer(
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

// --- Nomi Wikidata risolti "a richiesta" (lazy) ---
// Le query mondiali (basi/ospedali/strategici) caricano SOLO le coordinate, per
// restare veloci; il nome dell'entita' lo risolviamo al volo quando si apre il
// fumetto (via api/wdlabel -> wbgetentities). Cache di promesse per QID.
const _wdLabelCache = new Map();
function wdLabel(qid) {
  if (!qid) return Promise.resolve("");
  if (_wdLabelCache.has(qid)) return _wdLabelCache.get(qid);
  const p = fetch("api/wdlabel?ids=" + encodeURIComponent(qid))
    .then(r => r.json()).then(d => (d && d[qid]) || "").catch(() => "");
  _wdLabelCache.set(qid, p);
  return p;
}
// Marker per i layer "intel" (Wikidata): fumetto con nome (risolto al volo) +
// tipo + link Wikidata (che si apre nella finestra interna).
function intelMarker(c, p, color, fallback, kindLabel, layer) {
  const rows = () => [[kindLabel, esc(p.kind || "")]];
  const links = () => [["Wikidata", p.wd ? "https://www.wikidata.org/wiki/" + p.wd : ""]];
  const mk = L.circleMarker([c[1], c[0]], dot(color, 5))
    .bindPopup(popup(p.name || fallback, rows(), links()), { maxWidth: 260 });
  mk.on("popupopen", () => {
    if (!p.wd || p.name) return;             // gia' risolto: niente
    wdLabel(p.wd).then(nm => {
      if (nm) { p.name = nm; mk.setPopupContent(popup(nm, rows(), links())); }
    });
  });
  mk.addTo(layer);
  return mk;
}

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
  {
    // Starlink: costellazione SpaceX (~6000). Layer SEPARATO, spento di default
    // (spunta a parte): si carica solo se acceso, cosi' chi non lo vuole non
    // paga marker/CPU. TLE dal gruppo "starlink" di CelesTrak (vedi startSats).
    id: "starlink", nome: "Starlink", color: "#7dd3fc",
    desc: "CelesTrak - costellazione SpaceX (~6000, calcolata live)",
    render() { return 0; },
  },
  {
    id: "military", nome: "Basi militari", color: "#d1495b",
    desc: "Installazioni militari nel mondo (Wikidata), caricate una volta",
    render(data, layer) {
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        intelMarker(c, f.properties, "#d1495b", "Sito militare", "Tipo", layer);
        n++;
      });
      return n;
    },
  },
  {
    id: "hospitals", nome: "Ospedali", color: "#2ec4b6",
    desc: "Ospedali nel mondo (Wikidata), caricati una volta",
    render(data, layer) {
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        intelMarker(c, f.properties, "#2ec4b6", "Ospedale", "Tipo", layer);
        n++;
      });
      return n;
    },
  },
  {
    id: "strategic", nome: "Punti strategici", color: "#f4a259",
    desc: "Infrastrutture critiche nel mondo (Wikidata): centrali, aeroporti, dighe, porti",
    render(data, layer) {
      let n = 0;
      (data.features || []).forEach(f => {
        const c = f.geometry && f.geometry.coordinates; if (!c) return;
        intelMarker(c, f.properties, "#f4a259", "Punto strategico", "Categoria", layer);
        n++;
      });
      return n;
    },
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
function startFeed(id) { if (SAT_LAYERS[id]) startSats(id); else startLayer(id); }
function stopFeed(id) { if (SAT_LAYERS[id]) stopSats(id); else stopLayer(id); }

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
  // Layer OSM GLOBALI (punti fissi): scaricati una volta a livello mondiale e
  // tenuti in IndexedDB (persistono tra sessioni). Refresh raro (12h).
  military:  { live: false, interval: 43200 },
  hospitals: { live: false, interval: 43200 },
  strategic: { live: false, interval: 43200 },
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
    // Layer bbox (OSM): quando l'area e' troppo ampia il server risponde con un
    // "hint" e nessun elemento -> mostriamo l'invito a ingrandire, non "0".
    if (body.hint && !(body.features && body.features.length)) {
      layers[id].clearLayers();
      cnt.textContent = "⤢"; cnt.classList.remove("err"); cnt.title = body.hint;
      feedMsg(body.hint);
      return;
    }
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
  goes: "GOES", science: "Scienza", geo: "Geostazionari", starlink: "Starlink",
};
// Due layer satellitari, ciascuno con i suoi TLE/record: "satellites" (set
// curato) e "starlink" (costellazione SpaceX, ~6000, caricata a parte solo se
// l'utente accende la spunta). Stato per-layer per non mischiarli.
const SAT_LAYERS = {
  satellites: { query: "api/tle", color: "#e0b3ff", radius: 3, label: "Satelliti", redrawMs: 1000 },
  // Starlink e' ~10k satelliti: ridisegnarli ogni secondo saturerebbe il WebKit
  // software della distro, quindi lo ricalcoliamo piu' di rado (movimento ancora
  // fluido a queste quote).
  starlink: { query: "api/tle?group=starlink", color: "#7dd3fc", radius: 2, label: "Starlink", redrawMs: 3000 },
};
const satState = {
  satellites: { recs: [], ts: 0, loading: false },
  starlink: { recs: [], ts: 0, loading: false },
};

async function loadTLE(id) {
  const st = satState[id], cfg = SAT_LAYERS[id];
  if (st.loading) return;
  st.loading = true;
  const cnt = feedEl(id).querySelector(".cnt");
  cnt.textContent = "..."; cnt.classList.remove("err");
  try {
    const d = await (await fetch(cfg.query)).json();
    const sats = d.sats || [];
    if (!sats.length) throw new Error(d.error || "nessun TLE disponibile");
    const recs = [];
    sats.forEach(s => {
      try {
        const rec = satellite.twoline2satrec(s.l1, s.l2);
        if (rec && !rec.error) recs.push({ name: s.name, group: s.group, satrec: rec });
      } catch (e) { /* TLE malformato: salta */ }
    });
    st.recs = recs; st.ts = Date.now();
    feedMsg("");
  } catch (e) {
    cnt.textContent = "!"; cnt.classList.add("err"); cnt.title = String(e.message || e);
    feedMsg(cfg.label + ": " + (e.message || e));
  } finally { st.loading = false; }
}

function drawSats(id) {
  const st = satState[id], cfg = SAT_LAYERS[id];
  if (!active[id] || !window.satellite || !st.recs.length) return;
  const now = new Date();
  const gmst = satellite.gstime(now);
  const layer = layers[id];
  layer.clearLayers();
  let n = 0;
  for (let i = 0; i < st.recs.length; i++) {
    const s = st.recs[i];
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
    L.circleMarker([lat, lon], dot(cfg.color, cfg.radius))
      .bindPopup(popup(s.name || "Satellite", rows,
        [["Scheda N2YO", "https://www.n2yo.com/?s=" + (s.satrec.satnum || "")]]),
        { maxWidth: 260 })
      .addTo(layer);
    n++;
  }
  feedEl(id).querySelector(".cnt").textContent = n;
}

async function startSats(id) {
  if (!window.satellite) { feedMsg("satellite.js non caricato"); return; }
  const st = satState[id];
  if (!st.recs.length || Date.now() - st.ts > 7200000) await loadTLE(id);
  drawSats(id);
}
function stopSats(id) { /* lo scheduler smette di ridisegnare quando inattivo */ }

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
    if (panel === "report") loadSavedReports();
  });
});

// ---------------------------------------------------------------------------
// Elenco dei dossier salvati nella loot (apri HTML / scarica JSON).
// ---------------------------------------------------------------------------
function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
  return (n / 1048576).toFixed(1) + " MB";
}
async function loadSavedReports() {
  const ul = document.getElementById("saved-list");
  if (!ul) return;
  ul.innerHTML = '<li class="empty">Carico…</li>';
  try {
    const r = await fetch("api/reports");
    const d = await r.json();
    const list = d.reports || [];
    if (!list.length) { ul.innerHTML = '<li class="empty">Nessun dossier salvato finora.</li>'; return; }
    ul.innerHTML = "";
    list.forEach(rep => {
      const li = document.createElement("li");
      const when = new Date(rep.mtime * 1000).toLocaleString();
      const label = rep.title || rep.name;
      const openUrl = "api/report/file?name=" + encodeURIComponent(rep.name);
      const jsonUrl = "api/report/file?dl=1&name=" + encodeURIComponent(rep.name.replace(/\.html$/, ".json"));
      const nv = (rep.entries != null) ? (" · " + rep.entries + " voci") : "";
      li.innerHTML =
        '<div class="sv-main">' +
        (rep.demo ? '<span class="sv-badge">DEMO</span> ' : "") +
        '<span class="sv-title">' + esc(label) + "</span>" +
        '<span class="sv-meta">' + esc(when) + nv + " · " + fmtBytes(rep.size) + "</span></div>" +
        '<div class="sv-act">' +
        (rep.json ? '<button class="mini-btn mini-btn-go" data-name="' + esc(rep.name) +
          '" data-id="' + esc(rep.id) + '" data-demo="' + (rep.demo ? "1" : "") +
          '">Nel dossier</button>' : "") +
        '<a class="mini-btn" href="' + openUrl + '" target="_blank" rel="noopener">Apri</a>' +
        (rep.json ? '<a class="mini-btn" href="' + jsonUrl + '">JSON</a>' : "") +
        '<button class="mini-btn mini-btn-del" data-name="' + esc(rep.name) +
          '" data-label="' + esc(label) + '" title="Elimina il fascicolo">&#128465;</button>' +
        "</div>";
      ul.appendChild(li);
    });
    ul.querySelectorAll(".mini-btn-go").forEach(b => b.addEventListener("click", () => {
      loadCase(b.dataset.name, b.dataset.id, b.dataset.demo === "1");
    }));
    ul.querySelectorAll(".mini-btn-del").forEach(b => b.addEventListener("click", () => {
      deleteCase(b.dataset.name, b.dataset.label);
    }));
  } catch (e) {
    ul.innerHTML = '<li class="empty">Errore nel caricare l\'elenco.</li>';
  }
}
(function () {
  const b = document.getElementById("saved-refresh");
  if (b) b.addEventListener("click", loadSavedReports);
})();

// Conferma grafica integrata nel tema (sostituisce confirm() nativo). Ritorna
// una Promise<boolean>. Enter = conferma, Esc / clic fuori = annulla.
function hConfirm(message, opts) {
  opts = opts || {};
  return new Promise(resolve => {
    const modal = document.getElementById("confirm-modal");
    if (!modal) { resolve(window.confirm(message)); return; }
    const msg = document.getElementById("confirm-msg");
    const title = document.getElementById("confirm-title");
    const ok = document.getElementById("confirm-ok");
    const cancel = document.getElementById("confirm-cancel");
    title.textContent = opts.title || "Conferma";
    msg.innerHTML = esc(String(message)).replace(/\n/g, "<br>");
    ok.textContent = opts.ok || "Conferma";
    cancel.textContent = opts.cancel || "Annulla";
    ok.className = "btn" + (opts.danger ? " btn-danger" : "");
    modal.hidden = false;
    const done = (val) => {
      modal.hidden = true;
      ok.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      document.removeEventListener("keydown", onKey, true);
      modal.removeEventListener("click", onBackdrop);
      resolve(val);
    };
    const onOk = () => done(true);
    const onCancel = () => done(false);
    const onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); done(false); }
      else if (e.key === "Enter") { e.preventDefault(); done(true); }
    };
    const onBackdrop = (e) => { if (e.target === modal) done(false); };
    ok.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
    document.addEventListener("keydown", onKey, true);
    modal.addEventListener("click", onBackdrop);
    ok.focus();
  });
}

// Elimina un fascicolo (html + json) dopo conferma.
async function deleteCase(name, label) {
  const ok = await hConfirm(
    'Eliminare definitivamente il fascicolo "' + (label || name) + '"?\n' +
    "Rimuove sia l'HTML sia il JSON dalla loot. L'operazione non è annullabile.",
    { title: "Elimina fascicolo", ok: "Elimina", danger: true });
  if (!ok) return;
  try {
    const r = await fetch("api/report/delete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name }),
    });
    const b = await r.json();
    if (b.ok) {
      // se stavo lavorando proprio su questo fascicolo, scollego l'identità
      const stem = name.replace(/\.html$/, "");
      if (currentCase && currentCase.id === stem) { currentCase = null; updateCaseIndicator(); }
    }
    loadSavedReports();
    if (typeof HORUS_refreshCasesPanel === "function") HORUS_refreshCasesPanel();
  } catch (e) { /* silenzioso */ }
}

// Pannello "Fascicoli" dentro il Centro Correlazioni: elenca i fascicoli e
// permette di riprenderli (carica nel dossier + apre il grafo) o eliminarli.
let casesPanelOpen = false;
async function openCasesPanel() {
  if (window.HORUS_openCorrelate) window.HORUS_openCorrelate();
  const body = document.getElementById("corr-body");
  if (!body) return;
  casesPanelOpen = true;
  body.innerHTML = '<p class="corr-empty">Carico i fascicoli…</p>';
  try {
    const d = await (await fetch("api/reports")).json();
    const list = d.reports || [];
    const openBar = (currentCase && currentCase.id) || dossier.length
      ? '<button class="corr-btn cr-close" style="margin-bottom:8px">&#10005; Chiudi fascicolo aperto</button>'
      : "";
    if (!list.length) {
      body.innerHTML = openBar + '<p class="corr-empty">Nessun fascicolo salvato. Costruiscine uno e premi “Salva”.</p>';
      const cx = body.querySelector(".cr-close"); if (cx) cx.addEventListener("click", closeCase);
      return;
    }
    let h = openBar + '<div class="case-list">';
    list.forEach(r => {
      const when = new Date(r.mtime * 1000).toLocaleString();
      const nv = (r.entries != null) ? (r.entries + " voci · ") : "";
      h += '<div class="case-row">' +
        '<div class="case-info">' + (r.demo ? '<span class="sv-badge">DEMO</span> ' : "") +
        '<span class="case-t">' + esc(r.title || r.name) + '</span>' +
        '<span class="case-m">' + nv + esc(when) + '</span></div>' +
        '<div class="case-act">' +
        (r.json ? '<button class="corr-btn cr-go" data-name="' + esc(r.name) + '" data-id="' + esc(r.id) +
          '" data-demo="' + (r.demo ? "1" : "") + '">Riprendi</button>' : "") +
        '<button class="corr-btn cr-del" data-name="' + esc(r.name) + '" data-label="' + esc(r.title || r.name) +
          '" title="Elimina">&#128465;</button></div></div>';
    });
    h += "</div>";
    body.innerHTML = h;
    body.querySelectorAll(".cr-go").forEach(b => b.addEventListener("click", () => {
      loadCase(b.dataset.name, b.dataset.id, b.dataset.demo === "1");
    }));
    body.querySelectorAll(".cr-del").forEach(b => b.addEventListener("click", () => {
      deleteCase(b.dataset.name, b.dataset.label);
    }));
    const cx = body.querySelector(".cr-close"); if (cx) cx.addEventListener("click", closeCase);
  } catch (e) {
    body.innerHTML = '<p class="corr-empty">Errore nel caricare i fascicoli.</p>';
  }
}
function HORUS_refreshCasesPanel() { if (casesPanelOpen) openCasesPanel(); }
(function () {
  const b = document.getElementById("corr-cases-btn");
  if (b) b.addEventListener("click", openCasesPanel);
})();

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

// --- Finestra telecamera ingrandibile (come reader/live/webwin) --------------
// Clic su una telecamera del fumetto -> finestra interna ridimensionabile con
// immagine/clip in diretta che continua a rinfrescarsi. Le foto non-telecamera
// (es. vulcani) restano sul lightbox semplice.
const camwinEl = document.getElementById("camwin");
const camwinImg = document.getElementById("camwin-img");
const camwinVid = document.getElementById("camwin-vid");
let camwinTimer = null;
function closeCam() {
  camwinEl.hidden = true;
  if (camwinTimer) { clearInterval(camwinTimer); camwinTimer = null; }
  camwinImg.removeAttribute("src");
  try { camwinVid.pause(); } catch (e) {}
  camwinVid.removeAttribute("src");
}
function openCam(o) {
  document.getElementById("camwin-title").textContent = o.title || "Telecamera";
  document.getElementById("camwin-net").textContent = o.net || "";
  const ext = document.getElementById("camwin-ext");
  if (o.extUrl) { ext.href = o.extUrl; ext.hidden = false; } else { ext.hidden = true; }
  if (camwinTimer) { clearInterval(camwinTimer); camwinTimer = null; }
  if (o.video) {
    camwinImg.hidden = true; camwinVid.hidden = false;
    camwinVid.src = o.video; camwinVid.play().catch(() => {});
  } else {
    camwinVid.hidden = true; try { camwinVid.pause(); } catch (e) {}
    camwinVid.removeAttribute("src");
    camwinImg.hidden = false;
    const base = o.image;
    const bust = () => { camwinImg.src = base + (base.indexOf("?") < 0 ? "?" : "&") + "t=" + Date.now(); };
    bust();
    if (o.live) camwinTimer = setInterval(bust, 6000);   // JPEG che si rinnova
  }
  camwinEl.classList.remove("expanded");
  camwinEl.hidden = false;
}
function openCamFromEl(el) {
  const pop = el.closest(".cam-pop");
  const b = pop && pop.querySelector("b");
  const net = pop && pop.querySelector(".cam-net");
  const a = pop && pop.querySelector("a[href]");
  const isVid = el.tagName === "VIDEO";
  openCam({
    title: b ? b.textContent : "Telecamera",
    net: net ? net.textContent.trim() : "",
    extUrl: a ? a.href : "",
    video: isVid ? el.getAttribute("data-src") : "",
    image: isVid ? "" : el.getAttribute("data-src"),
    live: !isVid,
  });
}
document.getElementById("camwin-close").addEventListener("click", closeCam);
document.getElementById("camwin-expand").addEventListener("click",
  () => camwinEl.classList.toggle("expanded"));

document.addEventListener("click", e => {
  // Telecamera del traffico (immagine live o clip): finestra ingrandibile.
  const cam = e.target.closest("img.cam-live, video.cam-vid");
  if (cam) { openCamFromEl(cam); return; }
  // Altre immagini .cam (foto vulcani ecc.): lightbox semplice.
  const img = e.target.closest("img.cam");
  if (img && img.src) { openLightbox(img.src); }
});
lightbox.addEventListener("click", e => {
  if (e.target === lightbox || e.target.id === "lightbox-close") closeLightbox();
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { closeLightbox(); closeCam(); }
});

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
    if (!active[id] || SAT_LAYERS[id]) return;   // i satelliti hanno il loro giro
    if (dueAt[id] == null) dueAt[id] = now;
    if (now >= dueAt[id]) { pollLayer(id); dueAt[id] = now + cadence(id); }
  });
  // Satelliti (curati + Starlink): ricalcolo posizioni ogni secondo (movimento
  // fluido); TLE ogni 2h. Ogni layer satellitare gira solo se acceso.
  Object.keys(SAT_LAYERS).forEach(id => {
    if (!active[id]) return;
    const st = satState[id];
    if (!st.loading && now - st.ts > 7200000) loadTLE(id);
    if (!popupOpen && now - (st.lastDraw || 0) >= SAT_LAYERS[id].redrawMs) {
      drawSats(id); st.lastDraw = now;
    }
  });
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
// Fascicolo corrente: se aperto da uno salvato, `id` è il suo case_id e
// "Salva" lo RISCRIVE (continuazione). null = fascicolo nuovo, non ancora salvato.
let currentCase = null;
const caseLayer = L.layerGroup().addTo(map);
function plotCaseEntries() {
  caseLayer.clearLayers();
  dossier.forEach(e => {
    if (typeof e.lat !== "number" || typeof e.lon !== "number") return;
    // Con una finestra temporale attiva, fuori-finestra = marcatore attenuato.
    const on = (typeof inCaseWindow === "function") ? inCaseWindow(e) : true;
    L.circleMarker([e.lat, e.lon], { radius: on ? 6 : 4, color: "#ffb000",
      weight: on ? 2 : 1, fillColor: "#ffb000", fillOpacity: on ? .5 : .12,
      opacity: on ? 1 : .3 })
      .bindPopup(popup(dossierLabel(e.type) + ": " + e.title,
        [["Quando", esc(e.time)], ["Fonte", esc(e.via || "")]]))
      .addTo(caseLayer);
  });
}
function updateCaseIndicator() {
  const box = document.getElementById("case-indicator");
  if (!box) return;
  const t = (document.getElementById("report-title").value || "").trim();
  let openish = false;
  if (currentCase && currentCase.id) {
    box.innerHTML = '<span class="ci-on">&#128194; Fascicolo aperto: <b>' +
      esc(t || currentCase.id) + '</b> — "Salva" aggiorna questo fascicolo.</span>';
    box.hidden = false; openish = true;
  } else if (dossier.length) {
    box.innerHTML = '<span class="ci-new">&#128196; Nuovo fascicolo (non ancora salvato).</span>';
    box.hidden = false; openish = true;
  } else { box.hidden = true; }
  // Il pulsante "Chiudi fascicolo" compare tra i pulsanti del tab Report solo
  // quando c'e' qualcosa da chiudere (comodo averlo qui oltre che nel Centro
  // Correlazioni).
  const rc = document.getElementById("report-close");
  if (rc) rc.hidden = !openish;
}
// Chiude la vista del fascicolo (NON lo salva né lo elimina): svuota la working
// set, toglie i suoi punti dalla mappa, chiude grafo e pannello fascicoli e
// torna alla visualizzazione normale del mappamondo.
async function closeCase() {
  if (dossier.length && !(currentCase && currentCase.id)) {
    const ok = await hConfirm(
      "Chiudere il fascicolo senza salvarlo?\nLe voci non salvate andranno perse.",
      { title: "Chiudi fascicolo", ok: "Chiudi senza salvare", danger: true });
    if (!ok) return;
  }
  dossier.length = 0;
  currentCase = null;
  caseLayer.clearLayers();
  document.getElementById("report-title").value = "";
  document.getElementById("report-objective").value = "";
  renderDossier();
  updateCaseIndicator();
  try { window.HORUS_graphSVG = ""; } catch (e) {}
  const gw = document.getElementById("graphwin"); if (gw) gw.hidden = true;
  if (typeof casesPanelOpen !== "undefined" && casesPanelOpen) {
    casesPanelOpen = false;
    const body = document.getElementById("corr-body"); if (body) body.innerHTML = "";
  }
  const note = document.getElementById("report-note");
  if (note) note.textContent = "Fascicolo chiuso: sei tornato alla vista normale.";
}
async function loadCase(name, id, isDemo) {
  const note = document.getElementById("report-note");
  try {
    const r = await fetch("api/report/file?name=" + encodeURIComponent(name.replace(/\.html$/, ".json")));
    if (!r.ok) throw new Error("JSON non trovato");
    const c = await r.json();
    dossier.length = 0;
    (c.entries || []).forEach(e => dossier.push(e));
    document.getElementById("report-title").value = c.title || "";
    document.getElementById("report-operator").value = c.operator || "";
    document.getElementById("report-objective").value = c.objective || "";
    // Aprire una DEMO NON la lega: al salvataggio se ne crea uno nuovo, così la
    // demo resta intatta.
    currentCase = isDemo ? null : { id: c.case_id || id };
    renderDossier();
    plotCaseEntries();
    updateCaseIndicator();
    // Integrazione diretta nel Centro Correlazioni: apre la plancia e disegna
    // subito il grafo del fascicolo, come se lo stessi ancora costruendo.
    if (window.HORUS_openCorrelate) window.HORUS_openCorrelate();
    if (window.HORUS_openGraph) window.HORUS_openGraph();
    if (note) note.textContent = isDemo
      ? "Demo caricata nel dossier: modificala e salvala come nuovo fascicolo."
      : ("Fascicolo aperto (" + dossier.length + " voci). Aggiungi dati e salva per aggiornarlo.");
  } catch (e) {
    if (note) note.textContent = "Impossibile aprire il fascicolo: " + (e.message || e);
  }
}
function newCase() {
  dossier.length = 0;
  currentCase = null;
  caseLayer.clearLayers();
  document.getElementById("report-title").value = "";
  document.getElementById("report-objective").value = "";
  renderDossier();
  updateCaseIndicator();
  const note = document.getElementById("report-note");
  if (note) note.textContent = "Nuovo fascicolo vuoto.";
}
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
  if (extra.img) e.img = extra.img;                 // schermata (data URL PNG)
  dossier.push(e);
  renderDossier();
}
const DOSSIER_LABEL = {
  geoint: "GEOINT", recon: "Ricognizione", socmint: "SOCMINT",
  email: "Email", correlazione: "Correlazione", area: "Area",
  exif: "Metadati foto", nota: "Nota", news: "Notizia", screenshot: "Schermata",
};
function dossierLabel(t) { return DOSSIER_LABEL[t] || t; }
function renderDossier() {
  const ul = document.getElementById("report-list");
  const stats = document.getElementById("report-stats");
  ul.innerHTML = "";
  if (!dossier.length) {
    ul.innerHTML = '<li class="empty">Ancora nessuna voce. Esegui una recon o un GEOINT.</li>';
    if (stats) stats.innerHTML = "";
    caseWindow = null;
    renderTimeline();          // dossier vuoto -> nasconde la timeline
    plotCaseEntries();
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
    li.dataset.i = i;
    if (!inCaseWindow(e)) li.classList.add("tl-out");
    let meta = e.time + " · " + esc(e.via);
    if (e.lat != null) meta += " · &#128205; " + e.lat.toFixed(4) + ", " + e.lon.toFixed(4);
    const thumb = e.img ? '<img class="rep-thumb" src="' + e.img + '" alt="schermata">' : "";
    li.innerHTML = '<div class="rk">' + esc(dossierLabel(e.type)) + "</div><div class='rt'>" +
      esc(e.title) + "</div>" + thumb + "<div class='rd'>" + meta + "</div>" +
      '<button class="rep-del" data-i="' + i + '" title="Rimuovi questa voce">&times;</button>';
    ul.appendChild(li);
  });
  ul.querySelectorAll(".rep-del").forEach(b => b.addEventListener("click", (ev) => {
    ev.stopPropagation();
    dossier.splice(parseInt(b.dataset.i, 10), 1); renderDossier();
  }));
  renderTimeline();
  plotCaseEntries();
  updateCaseIndicator();
}

// --- Timeline temporale del fascicolo --------------------------------------
// Una striscia con un punto per ogni voce datata; trascinando si seleziona una
// finestra che evidenzia le voci (elenco + marcatori sulla mappa) in quel
// periodo. Un clic su un punto porta la mappa sulla voce (se georiferita).
let caseWindow = null;                     // {from, to} in ms, oppure null = tutto
function entryMs(e) {
  const t = Date.parse(e.iso || "");
  if (!isNaN(t)) return t;
  const t2 = Date.parse(e.time || "");
  return isNaN(t2) ? null : t2;
}
function inCaseWindow(e) {
  if (!caseWindow) return true;
  const t = entryMs(e);
  if (t == null) return true;              // voci senza data: sempre visibili
  return t >= caseWindow.from && t <= caseWindow.to;
}
const TL_TYPE_COLOR = {
  geoint: "#00e5ff", recon: "#7dffa8", socmint: "#b78cff", email: "#ffd166",
  area: "#ff9a5a", correlazione: "#7ee0ff", exif: "#ff5a8a", news: "#c8f5ff", nota: "#5a8a9a",
  screenshot: "#9aa7b0",
};
function renderTimeline() {
  const box = document.getElementById("report-timeline");
  const svg = document.getElementById("tl-svg");
  if (!box || !svg) return;
  const dated = dossier.map((e, i) => ({ i: i, t: entryMs(e), e: e })).filter(x => x.t != null);
  if (dated.length < 2) { box.hidden = true; caseWindow = null; return; }
  box.hidden = false;
  let tmin = Math.min.apply(null, dated.map(x => x.t));
  let tmax = Math.max.apply(null, dated.map(x => x.t));
  if (tmax === tmin) tmax = tmin + 1;
  const W = 100, H = 30, pad = 3;
  const X = t => pad + (t - tmin) / (tmax - tmin) * (W - 2 * pad);
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("preserveAspectRatio", "none");
  let inner = '<line x1="' + pad + '" y1="' + (H / 2) + '" x2="' + (W - pad) +
    '" y2="' + (H / 2) + '" class="tl-axis"/>';
  if (caseWindow) {
    const x1 = X(Math.max(tmin, caseWindow.from)), x2 = X(Math.min(tmax, caseWindow.to));
    inner += '<rect x="' + x1 + '" y="2" width="' + Math.max(0.5, x2 - x1) +
      '" height="' + (H - 4) + '" class="tl-brush"/>';
  }
  dated.forEach(x => {
    const col = TL_TYPE_COLOR[x.e.type] || "#00e5ff";
    const on = inCaseWindow(x.e);
    inner += '<circle cx="' + X(x.t).toFixed(2) + '" cy="' + (H / 2) +
      '" r="' + (on ? 2.4 : 1.6) + '" fill="' + col + '" fill-opacity="' +
      (on ? 1 : 0.3) + '" class="tl-dot" data-i="' + x.i + '"><title>' +
      esc(dossierLabel(x.e.type) + " · " + (x.e.time || "")) + "</title></circle>";
  });
  svg.innerHTML = inner;
  const fmt = ms => new Date(ms).toLocaleDateString();
  const rng = document.getElementById("tl-range");
  if (rng) rng.textContent = caseWindow
    ? (fmt(caseWindow.from) + " – " + fmt(caseWindow.to))
    : (fmt(tmin) + " – " + fmt(tmax));
  const reset = document.getElementById("tl-reset");
  if (reset) reset.hidden = !caseWindow;
  // interazione: drag = finestra; clic su un punto = vai alla voce
  svg._tl = { tmin: tmax === tmin ? tmin : tmin, tmax: tmax, W: W, pad: pad };
}
(function initTimeline() {
  const svg = document.getElementById("tl-svg");
  const reset = document.getElementById("tl-reset");
  if (!svg) return;
  const tAt = (clientX) => {
    const r = svg.getBoundingClientRect();
    const st = svg._tl; if (!st) return null;
    const frac = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    // riconverti da coord X (con pad) a tempo
    const xLogic = frac * st.W;
    const inner = Math.max(0, Math.min(1, (xLogic - st.pad) / (st.W - 2 * st.pad)));
    return st.tmin + inner * (st.tmax - st.tmin);
  };
  let down = null, moved = false;
  svg.addEventListener("pointerdown", ev => {
    down = tAt(ev.clientX); moved = false;
    try { svg.setPointerCapture(ev.pointerId); } catch (e) {}
  });
  svg.addEventListener("pointermove", ev => {
    if (down == null) return;
    const t = tAt(ev.clientX);
    if (t == null) return;
    if (Math.abs(ev.movementX) > 0) moved = true;
    caseWindow = { from: Math.min(down, t), to: Math.max(down, t) };
    renderDossier();
  });
  svg.addEventListener("pointerup", ev => {
    try { svg.releasePointerCapture(ev.pointerId); } catch (e) {}
    if (!moved) {
      // clic secco: se su un punto vai alla voce; altrimenti azzera finestra
      const dot = ev.target.closest && ev.target.closest(".tl-dot");
      if (dot) {
        const e = dossier[parseInt(dot.dataset.i, 10)];
        if (e && e.lat != null && e.lon != null) { map.setView([e.lat, e.lon], Math.max(map.getZoom(), 6)); }
        const li = document.querySelector('#report-list li[data-i="' + dot.dataset.i + '"]');
        if (li) { li.classList.add("rep-flash"); setTimeout(() => li.classList.remove("rep-flash"), 1200);
          li.scrollIntoView({ block: "nearest" }); }
      } else { caseWindow = null; renderDossier(); }
    } else if (caseWindow && (caseWindow.to - caseWindow.from) < 1000) {
      caseWindow = null; renderDossier();     // finestra troppo stretta -> annulla
    }
    down = null;
  });
  if (reset) reset.addEventListener("click", () => { caseWindow = null; renderDossier(); });
})();
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
           case_id: (currentCase && currentCase.id) ? currentCase.id : "",
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
    if (b.case_id) { currentCase = { id: b.case_id }; updateCaseIndicator(); }
    note.textContent = b.path
      ? ("Fascicolo salvato (" + (b.case_id || "?") + "). HTML e JSON in ~/NexusSec-loot/horus/.")
      : (b.error || "errore");
    if (b.path) loadSavedReports();
  } catch (e) { note.textContent = "Errore: " + (e.message || e); }
});
document.getElementById("report-clear").addEventListener("click", newCase);
document.getElementById("report-close").addEventListener("click", closeCase);

// --- Esportazioni fascicolo: indicatori (CSV / STIX) + stampa PDF -----------
function _dl(name, text, mime) {                 // download via Blob (come SVG/GeoJSON)
  const blob = new Blob([text], { type: mime || "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
// Estrae gli indicatori (IP, dominio, email) da tutte le voci del dossier.
function extractIndicators() {
  const RE_EMAIL = /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g;
  const RE_IP = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
  const RE_DOMAIN = /\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b/gi;
  const BAD_TLD = /\.(html?|php|json|xml|css|js|png|jpe?g|gif|svg|txt|pdf|aspx?)$/i;
  const okIp = s => s.split(".").every(o => { const n = +o; return o.length && n >= 0 && n <= 255; });
  const map = new Map();                          // "type|value" -> {type,value,sources:Set}
  const add = (type, value, src) => {
    value = value.trim().toLowerCase(); if (!value) return;
    const k = type + "|" + value;
    if (!map.has(k)) map.set(k, { type: type, value: value, sources: new Set() });
    if (src) map.get(k).sources.add(src);
  };
  dossier.forEach(e => {
    const src = e.title || dossierLabel(e.type);
    const text = [e.detail || "", e.target || "", (e.tags || []).join(" ")].join(" ");
    (text.match(RE_EMAIL) || []).forEach(x => add("email", x, src));
    const emails = new Set((text.match(RE_EMAIL) || []).map(x => x.toLowerCase()));
    (text.match(RE_IP) || []).forEach(x => { if (okIp(x)) add("ipv4-addr", x, src); });
    (text.match(RE_DOMAIN) || []).forEach(x => {
      const d = x.toLowerCase();
      if (BAD_TLD.test(d) || /^\d+\.\d+\.\d+\.\d+$/.test(d)) return;
      let inMail = false; emails.forEach(m => { if (m.endsWith("@" + d)) inMail = true; });
      if (!inMail) add("domain-name", d, src);
    });
  });
  return Array.from(map.values()).map(x => ({ type: x.type, value: x.value,
    sources: Array.from(x.sources) }));
}
function exportIndicatorsCSV() {
  const ind = extractIndicators();
  if (!ind.length) { document.getElementById("report-note").textContent = "Nessun indicatore nel dossier."; return; }
  const q = s => '"' + String(s).replace(/"/g, '""') + '"';
  let csv = "tipo,valore,fonti\n";
  ind.forEach(i => { csv += [q(i.type), q(i.value), q(i.sources.join("; "))].join(",") + "\n"; });
  _dl("horus-indicatori-" + Date.now() + ".csv", csv, "text/csv;charset=utf-8");
}
function _uuid() {
  return (crypto && crypto.randomUUID) ? crypto.randomUUID()
    : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0; return (c === "x" ? r : (r & 0x3 | 0x8)).toString(16); });
}
function buildSTIX(ind) {
  const now = new Date().toISOString();
  const pat = i => {
    if (i.type === "ipv4-addr") return "[ipv4-addr:value = '" + i.value + "']";
    if (i.type === "domain-name") return "[domain-name:value = '" + i.value + "']";
    if (i.type === "email") return "[email-addr:value = '" + i.value + "']";
    return "[x-misc:value = '" + i.value + "']";
  };
  const title = (document.getElementById("report-title").value || "HORUS dossier").trim();
  const objects = ind.map(i => ({
    type: "indicator", spec_version: "2.1", id: "indicator--" + _uuid(),
    created: now, modified: now, name: i.value,
    description: "Fonti: " + (i.sources.join("; ") || "—"),
    indicator_types: ["anomalous-activity"], pattern: pat(i),
    pattern_type: "stix", valid_from: now,
  }));
  return { type: "bundle", id: "bundle--" + _uuid(), _horus: title, objects: objects };
}
function exportIndicatorsSTIX() {
  const ind = extractIndicators();
  if (!ind.length) { document.getElementById("report-note").textContent = "Nessun indicatore nel dossier."; return; }
  _dl("horus-stix-" + Date.now() + ".json", JSON.stringify(buildSTIX(ind), null, 2), "application/json");
}
// HTML autonomo del fascicolo (usato sia dalla stampa/PDF sia dall'export ZIP).
// Include le schermate allegate (data URL PNG) e, se presente, il grafo relazioni.
function buildReportHTML() {
  const title = esc(document.getElementById("report-title").value.trim() || "Fascicolo HORUS");
  const op = esc(document.getElementById("report-operator").value.trim());
  const obj = esc(document.getElementById("report-objective").value.trim());
  const rows = dossier.map(e => {
    let meta = e.time + " · " + esc(e.via || "");
    if (e.lat != null) meta += " · " + e.lat.toFixed(4) + ", " + e.lon.toFixed(4);
    const shot = e.img ? '<div class="pi"><img src="' + e.img + '" alt="schermata"></div>' : "";
    return '<div class="pe"><div class="pk">' + esc(dossierLabel(e.type)) + '</div>' +
      '<div class="pt">' + esc(e.title || "") + '</div>' +
      '<div class="pd">' + esc(e.detail || "").replace(/\n/g, "<br>") + '</div>' +
      shot + '<div class="pm">' + meta + '</div></div>';
  }).join("");
  const gsvg = (typeof window.HORUS_graphSVG === "string") ? window.HORUS_graphSVG : "";
  return '<!doctype html><meta charset="utf-8"><title>' + title + '</title><style>' +
    'body{font:13px/1.5 system-ui,sans-serif;color:#111;margin:24px}' +
    'h1{font-size:20px;margin:0 0 4px}.sub{color:#555;margin:0 0 16px}' +
    '.pe{border:1px solid #ccc;border-radius:6px;padding:8px 10px;margin:0 0 8px;break-inside:avoid}' +
    '.pk{font-size:11px;color:#06c;font-weight:700;text-transform:uppercase}' +
    '.pt{font-weight:600;margin:2px 0}.pd{white-space:normal;color:#222}.pm{color:#777;font-size:11px;margin-top:4px}' +
    '.pi img{max-width:100%;border:1px solid #ccc;border-radius:6px;margin-top:6px}' +
    'svg{max-width:100%;height:auto;border:1px solid #ccc;border-radius:6px;margin-top:10px}' +
    '@media print{body{margin:0}}</style>' +
    '<h1>' + title + '</h1><p class="sub">' +
    (op ? "Operatore: " + op + " · " : "") + dossier.length + " voci" +
    (obj ? '<br>Obiettivo: ' + obj : "") + '</p>' + rows +
    (gsvg ? '<h2 style="font-size:15px">Grafo relazioni</h2>' + gsvg : "");
}
function buildDossierJSON() {
  return {
    tool: "HORUS", version: "2.1",
    title: document.getElementById("report-title").value.trim() || "",
    operator: document.getElementById("report-operator").value.trim() || "",
    objective: document.getElementById("report-objective").value.trim() || "",
    generated: new Date().toISOString(),
    entries: dossier,
  };
}
// Stampa/PDF: rende il fascicolo in un iframe e lo stampa (l'utente sceglie
// "Salva come PDF"). Niente popup: l'iframe e' affidabile.
function printDossierPDF() {
  if (!dossier.length) { document.getElementById("report-note").textContent = "Il dossier è vuoto."; return; }
  let ifr = document.getElementById("print-frame");
  if (!ifr) { ifr = document.createElement("iframe"); ifr.id = "print-frame";
    ifr.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0"; document.body.appendChild(ifr); }
  const doc = ifr.contentWindow.document;
  doc.open(); doc.write(buildReportHTML()); doc.close();
  setTimeout(() => { ifr.contentWindow.focus(); ifr.contentWindow.print(); }, 300);
}

// --- ZIP minimale (solo "store", nessuna compressione): niente dipendenze,
//     funziona offline. Sufficiente per impacchettare il bundle del dossier. ---
const _crcTable = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();
function _crc32(u8) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < u8.length; i++) c = _crcTable[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
function _toU8(d) { return (d instanceof Uint8Array) ? d : new TextEncoder().encode(String(d)); }
function _dataUrlToU8(u) {
  try {
    const bin = atob(u.split(",", 2)[1]);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch (e) { return null; }
}
function makeZip(files) {                       // files: [{name, data}]
  const enc = new TextEncoder();
  const chunks = []; const central = [];
  let offset = 0;
  const push = u => { chunks.push(u); offset += u.length; };
  files.forEach(f => {
    const nameU = enc.encode(f.name);
    const data = _toU8(f.data);
    const crc = _crc32(data);
    const lh = new DataView(new ArrayBuffer(30));
    lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true);
    lh.setUint16(6, 0x0800, true); lh.setUint16(8, 0, true);
    lh.setUint16(10, 0, true); lh.setUint16(12, 0x21, true);
    lh.setUint32(14, crc, true); lh.setUint32(18, data.length, true);
    lh.setUint32(22, data.length, true); lh.setUint16(26, nameU.length, true);
    lh.setUint16(28, 0, true);
    const localOffset = offset;
    push(new Uint8Array(lh.buffer)); push(nameU); push(data);
    const ch = new DataView(new ArrayBuffer(46));
    ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true);
    ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true);
    ch.setUint16(10, 0, true); ch.setUint16(12, 0, true); ch.setUint16(14, 0x21, true);
    ch.setUint32(16, crc, true); ch.setUint32(20, data.length, true);
    ch.setUint32(24, data.length, true); ch.setUint16(28, nameU.length, true);
    ch.setUint32(42, localOffset, true);
    central.push({ header: new Uint8Array(ch.buffer), name: nameU });
  });
  const centralStart = offset; let centralSize = 0;
  central.forEach(c => { push(c.header); push(c.name); centralSize += c.header.length + c.name.length; });
  const eo = new DataView(new ArrayBuffer(22));
  eo.setUint32(0, 0x06054b50, true); eo.setUint16(8, files.length, true);
  eo.setUint16(10, files.length, true); eo.setUint32(12, centralSize, true);
  eo.setUint32(16, centralStart, true);
  push(new Uint8Array(eo.buffer));
  return new Blob(chunks, { type: "application/zip" });
}
function exportDossierZIP() {
  const note = document.getElementById("report-note");
  if (!dossier.length) { note.textContent = "Il dossier è vuoto."; return; }
  note.textContent = "Creazione ZIP…";
  const files = [];
  files.push({ name: "report.html", data: buildReportHTML() });
  files.push({ name: "dossier.json", data: JSON.stringify(buildDossierJSON(), null, 2) });
  const ind = extractIndicators();
  if (ind.length) {
    const q = s => '"' + String(s).replace(/"/g, '""') + '"';
    let csv = "tipo,valore,fonti\n";
    ind.forEach(i => { csv += [q(i.type), q(i.value), q(i.sources.join("; "))].join(",") + "\n"; });
    files.push({ name: "indicatori.csv", data: csv });
    files.push({ name: "stix.json", data: JSON.stringify(buildSTIX(ind), null, 2) });
  }
  let n = 0;
  dossier.forEach(e => {
    if (e.img && e.img.indexOf("data:") === 0) {
      const b = _dataUrlToU8(e.img);
      if (b) files.push({ name: "schermate/shot-" + (++n) + ".png", data: b });
    }
  });
  try {
    _dlBlob("horus-dossier-" + Date.now() + ".zip", makeZip(files));
    note.textContent = "ZIP creato (" + files.length + " file).";
  } catch (e) { note.textContent = "Errore ZIP: " + (e.message || e); }
}
function _dlBlob(name, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}
// Aggiunge al dossier una schermata di cio' che l'analista vede ora (scrot lato
// backend). Utile come prova visiva nel report.
async function addScreenshotToDossier() {
  const note = document.getElementById("report-note");
  note.textContent = "Cattura schermata…";
  try {
    const d = await (await fetch("api/screenshot")).json();
    if (!d.png) { note.textContent = d.error || "cattura non riuscita"; return; }
    const now = new Date();
    addDossier("screenshot", "Schermata " + now.toLocaleString(), "", { img: d.png });
    note.textContent = "Schermata aggiunta al dossier.";
  } catch (e) { note.textContent = "Errore schermata: " + (e.message || e); }
}
document.getElementById("report-csv").addEventListener("click", exportIndicatorsCSV);
document.getElementById("report-stix").addEventListener("click", exportIndicatorsSTIX);
document.getElementById("report-pdf").addEventListener("click", printDossierPDF);
document.getElementById("report-zip").addEventListener("click", exportDossierZIP);
document.getElementById("report-shot").addEventListener("click", addScreenshotToDossier);

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
let newsSeq = 0;                          // annulla risposte di ricerche superate
// Scorrimento del ticker guidato da JS (requestAnimationFrame). Motivo: in
// software rendering (WebKitGTK della live / Chromium) l'animazione CSS su un
// layer con mask a volte NON parte finche' non si interagisce con la pagina, e
// un cambio di contenuto via DOM non fa ri-verniciare la striscia (restava
// "congelata" fino al refresh). Muovendo noi il transform a ogni frame lo
// scorrimento parte SEMPRE subito e il nuovo contenuto compare all'istante.
let tickerX = 0, tickerHalf = 0, tickerPaused = false, tickerLast = 0, tickerRAF = 0;
const TICKER_SPEED = 55;                   // px/s
function tickerFrame(ts) {
  if (!tickerLast) tickerLast = ts;
  const dt = Math.min(0.05, (ts - tickerLast) / 1000);
  tickerLast = ts;
  if (!tickerPaused && tickerHalf > 0) {
    tickerX -= TICKER_SPEED * dt;
    if (-tickerX >= tickerHalf) tickerX += tickerHalf;   // loop senza stacco
    tickerTrack.style.transform = "translateX(" + tickerX + "px)";
  }
  tickerRAF = requestAnimationFrame(tickerFrame);
}
function startTickerScroll() {
  tickerHalf = tickerTrack.scrollWidth / 2;  // contenuto duplicato una volta
  tickerX = 0; tickerLast = 0;
  tickerTrack.style.transform = "translateX(0)";
  if (!tickerRAF) tickerRAF = requestAnimationFrame(tickerFrame);
}
function stopTickerScroll() {              // per i messaggi fissi (loading, esito)
  tickerHalf = 0; tickerX = 0;
  tickerTrack.style.transform = "translateX(0)";
}
function newsFilters() {                    // finestra temporale + lingua (ricerca 360°)
  const df = document.getElementById("ticker-df");
  const lang = document.getElementById("ticker-lang");
  return { df: df ? df.value : "", lang: lang ? lang.value : "it" };
}
async function loadNews(query) {
  if (typeof query === "string") newsQuery = query.trim();
  const seq = ++newsSeq;
  const clearBtn = document.getElementById("ticker-q-clear");
  if (clearBtn) clearBtn.hidden = !newsQuery;
  let url = "api/news";
  if (newsQuery) {
    const f = newsFilters();
    url += "?q=" + encodeURIComponent(newsQuery) +
      (f.df ? "&df=" + f.df : "") + "&lang=" + encodeURIComponent(f.lang);
  }
  try {
    tickerTrack.textContent = newsQuery
      ? ("  Ricerca 360° in corso: " + newsQuery + " … (fino a ~30s)")
      : "  …";
    stopTickerScroll();
    const r = await fetch(url);
    const d = await r.json();
    if (seq !== newsSeq) return;          // arrivata una ricerca piu' recente
    // IMPORTANTE: il ticker è una striscia UNICA animata. In software rendering
    // (WebKit della live / Chromium) un layer animato troppo largo (oltre la
    // dimensione massima di superficie, ~16k px) fa CRASHARE il renderer. Quindi
    // limitiamo il numero di titoli e accorciamo i più lunghi: la striscia resta
    // ampiamente sotto la soglia anche con la ricerca (fino a ~80 risultati).
    const TICKER_MAX = 22, TITLE_MAX = 84;
    const clip = (s) => (s && s.length > TITLE_MAX) ? (s.slice(0, TITLE_MAX - 1) + "…") : (s || "");
    const arts = (d.articles || []).filter(a => a.title).slice(0, TICKER_MAX);
    if (!arts.length) {
      tickerTrack.textContent = newsQuery
        ? ("  Nessun risultato per “" + newsQuery + "”.")
        : "  Nessuna notizia al momento.";
      stopTickerScroll();
      return;
    }
    // Contenuto DUPLICATO: lo scorrimento JS ricicla a meta' larghezza -> loop senza stacco.
    const pre = newsQuery
      ? '<span class="news-scope">360°: ' + esc(clip(newsQuery)) + '</span><span class="sep">•</span>' : "";
    const build = () => arts.map(a => {
      const more = (a.sources_count > 1)
        ? ' <span class="news-more" title="' + esc((a.sources || []).join(", ")) +
          '">+' + (a.sources_count - 1) + ' fonti</span>' : "";
      return '<a class="news-item" href="' + esc(a.url) + '" data-title="' + esc(a.title) +
        '" data-src="' + esc(a.domain) + '">' + esc(clip(a.title)) +
        ' <span class="dom">(' + esc(a.domain) + ')</span>' + more + '</a>' +
        '<span class="sep">•</span>';
    }).join("");
    tickerTrack.innerHTML = pre + build() + pre + build();
    // Avvia lo scorrimento JS: parte subito e ri-vernicia col nuovo contenuto.
    startTickerScroll();
  } catch (e) {
    if (seq !== newsSeq) return;
    tickerTrack.textContent = "  News non disponibili (rete non raggiungibile).";
    stopTickerScroll();
  }
}
document.getElementById("ticker-label").addEventListener("click", () => {
  document.getElementById("ticker").classList.toggle("min");
});
(function () {                             // pausa lo scorrimento sotto il mouse
  const t = document.getElementById("ticker");
  if (!t) return;
  t.addEventListener("mouseenter", () => { tickerPaused = true; });
  t.addEventListener("mouseleave", () => { tickerPaused = false; });
})();
(function () {
  const q = document.getElementById("ticker-q");
  const clr = document.getElementById("ticker-q-clear");
  if (q) q.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); loadNews(q.value); }
  });
  if (clr) clr.addEventListener("click", () => { if (q) q.value = ""; loadNews(""); });
  // Cambiando finestra temporale o lingua rilancia la ricerca in corso.
  ["ticker-df", "ticker-lang"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", () => { if (newsQuery) loadNews(newsQuery); });
  });
})();

// Traduzione del titolo al passaggio del mouse (le news mondiali sono spesso in
// lingua straniera). Best-effort, con cache per non ri-tradurre lo stesso testo.
const _titleTrCache = {};
let _titleTrTimer = 0;
(function () {
  tickerTrack.addEventListener("mouseover", (ev) => {
    const a = ev.target.closest && ev.target.closest("a.news-item");
    if (!a) return;
    const orig = a.dataset.title || "";
    if (!orig || a.dataset.tr === "1") return;
    clearTimeout(_titleTrTimer);
    _titleTrTimer = setTimeout(async () => {
      let tr = _titleTrCache[orig];
      if (!tr) {
        try {
          const d = await (await fetch("api/translate", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ q: [orig], tl: "it" }),
          })).json();
          tr = (d.t && d.t[0]) || "";
          _titleTrCache[orig] = tr;
        } catch (e) { return; }
      }
      // Mostra la traduzione come tooltip su tutte le copie (striscia duplicata).
      if (tr && tr !== orig) {
        tickerTrack.querySelectorAll("a.news-item").forEach(el => {
          if (el.dataset.title === orig) { el.title = "🇮🇹 " + tr; el.dataset.tr = "1"; }
        });
      }
    }, 350);
  });
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
// "Nel fascicolo": aggiunge l'articolo aperto come voce del dossier corrente.
document.getElementById("reader-save").addEventListener("click", () => {
  const st = readerState;
  const url = (st && st.url) || document.getElementById("reader-ext").href || "";
  const title = (st && st.origTitle) || document.getElementById("reader-title").textContent || "";
  const src = (st && st.src) || document.getElementById("reader-src").textContent || "";
  if (!url && !title) return;
  const excerpt = (st && st.origParas) ? st.origParas.slice(0, 2).join(" ") : "";
  const detail = (src ? ("Fonte: " + src + "\n") : "") + url +
    (excerpt ? ("\n\n" + excerpt) : "");
  addDossier("news", title || url, detail, { target: url, tags: ["news"] });
  const b = document.getElementById("reader-save");
  const old = b.innerHTML; b.innerHTML = "&#10003; Aggiunta"; b.disabled = true;
  setTimeout(() => { b.innerHTML = old; b.disabled = false; }, 1600);
});
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

// --- Visore web interno: apre Wikidata/Wikipedia/Wikimedia/OSM DENTRO HORUS ---
// (via proxy api/embed che aggira X-Frame-Options) invece che in un tab esterno.
const EMBED_ALLOW = [
  "wikidata.org", "wikipedia.org", "wikimedia.org", "wikinews.org",
  "wikivoyage.org", "wikibooks.org", "wikisource.org", "openstreetmap.org",
  "n2yo.com",
];
function embeddableUrl(url) {
  try {
    const u = new URL(url, location.href);
    if (u.protocol !== "http:" && u.protocol !== "https:") return false;
    const h = u.hostname.toLowerCase();
    return EMBED_ALLOW.some(d => h === d || h.endsWith("." + d));
  } catch (e) { return false; }
}
const webwinEl = document.getElementById("webwin");
const webwinFrame = document.getElementById("webwin-frame");
const webwinMsg = document.getElementById("webwin-msg");
function openEmbed(url, title) {
  document.getElementById("webwin-title").textContent = title || "Scheda";
  document.getElementById("webwin-ext").href = url;
  webwinMsg.hidden = true;
  webwinFrame.hidden = false;
  webwinFrame.src = "api/embed?url=" + encodeURIComponent(url);
  webwinEl.classList.remove("expanded");
  webwinEl.hidden = false;
}
function closeEmbed() {
  webwinEl.hidden = true;
  webwinFrame.src = "about:blank";
}
webwinFrame.addEventListener("error", () => {
  webwinFrame.hidden = true; webwinMsg.hidden = false;
  webwinMsg.textContent = "Impossibile caricare la scheda. Usa “apri ↗” per aprirla nel browser.";
});
document.getElementById("webwin-close").addEventListener("click", closeEmbed);
document.getElementById("webwin-expand").addEventListener("click",
  () => webwinEl.classList.toggle("expanded"));

document.addEventListener("click", e => {
  const lv = e.target.closest("a.live-open");
  if (lv) { e.preventDefault(); openLive(); return; }
  const a = e.target.closest("a.news-item");
  if (a) { e.preventDefault(); openReader(a.getAttribute("href"), a.dataset.title, a.dataset.src); return; }
  // Link a domini enciclopedici (Wikidata/Wikipedia/OSM/N2YO...): finestra
  // interna. ECCEZIONE: i link "apri ↗" (classe linklike) delle finestre stesse
  // devono SEMPRE aprire il tab esterno, quindi NON li intercettiamo.
  const w = e.target.closest("a[href]");
  if (w && !w.classList.contains("linklike") && embeddableUrl(w.getAttribute("href"))) {
    e.preventDefault();
    openEmbed(w.href, w.textContent || "Scheda");
  }
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { closeReader(); closeLive(); closeEmbed(); }
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
    const eng = document.getElementById("set-news-engine");
    if (eng) eng.value = s.news_engine || "both";
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
  updateMapCacheStatus();
}

// --- Mappa offline: stato/azioni della cache tile (IndexedDB) ---
async function updateMapCacheStatus() {
  const el = document.getElementById("map-cache-status");
  if (!el) return;
  const n = await tileCount();
  el.textContent = n ? (n + " tile in cache (disponibili offline)")
                     : "cache vuota — precarica il mondo o naviga la mappa online";
}
(function wireMapCache() {
  const prime = document.getElementById("map-prime");
  const clear = document.getElementById("map-cache-clear");
  if (prime) prime.addEventListener("click", async () => {
    const el = document.getElementById("map-cache-status");
    const cur = Object.values(bases).find(b => map.hasLayer(b)) || bases["Nera (default)"];
    prime.disabled = true; clear.disabled = true;
    try {
      // z0..5 = 1365 tile: mondo intero a basso zoom, pochi MB, resta offline.
      await primeWorld(cur, 5, (done, total) => {
        if (el) el.textContent = "Precarico mondo… " + done + "/" + total;
      });
      await updateMapCacheStatus();
    } catch (e) { if (el) el.textContent = "Errore nel precarico: " + (e.message || e); }
    prime.disabled = false; clear.disabled = false;
  });
  if (clear) clear.addEventListener("click", async () => {
    await tileClear();
    await updateMapCacheStatus();
  });
})();

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
document.getElementById("settings-expand").addEventListener("click", () => {
  const c = document.querySelector("#settings .settings-card");
  if (c) c.classList.toggle("full");
});
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
  const eng = document.getElementById("set-news-engine");
  if (eng) body.news_engine = eng.value;
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
makeDraggable("webwin", "webwin-head");
makeDraggable("camwin", "camwin-head");
makeDraggable("correlate", "corr-head");

// Avvio
loadTools();
refreshStatus();
restoreActive();   // riattiva i layer che erano accesi (persistono al refresh)
