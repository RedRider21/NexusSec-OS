// ===========================================================================
// HORUS - Centro Correlazioni
// ---------------------------------------------------------------------------
// Il cuore "analista": si seleziona un DATO (un'area, un punto o un'entita')
// e HORUS raccoglie da TUTTI i layer cio' che vi ricade nello spazio e nel
// tempo, calcola quali satelliti stanno sorvolando, e permette di tracciare
// il percorso di un'entita' in movimento. Tutto in locale, leggendo i dati
// gia' accumulati in IndexedDB dal motore di streaming di app.js.
//
// Dipende da variabili/funzioni globali dichiarate in app.js (stesso realm):
//   map, FEEDS, active, layers, dbGet, satRecs, satellite, addDossier,
//   esc, popup, dot, GROUP_IT, when, toggleFeed
// ===========================================================================
(function () {
  "use strict";

  const R = 6371;                       // raggio terrestre (km)
  const D2R = Math.PI / 180;
  function haversine(a, b) {            // distanza in km tra {lat,lon}
    const dLat = (b.lat - a.lat) * D2R, dLon = (b.lon - a.lon) * D2R;
    const s = Math.sin(dLat / 2) ** 2 +
      Math.cos(a.lat * D2R) * Math.cos(b.lat * D2R) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(s));
  }
  const LAYER_NAME = {
    quakes: "Terremoti", volcano: "Vulcani", fires: "Incendi",
    flights: "Voli", ships: "Navi", iss: "ISS", cameras: "Telecamere",
    satellites: "Satelliti", photo: "Foto (EXIF)",
  };
  const LAYER_COLOR = {
    quakes: "#ff5a8a", volcano: "#ff8c42", fires: "#ffb000", flights: "#00e5ff",
    ships: "#5b8cff", iss: "#a06bff", cameras: "#ff5ac8", satellites: "#e0b3ff",
    photo: "#ffe066",
  };

  // --- Estrazione entita' normalizzate dai dati grezzi di ogni feed ---------
  // Ritorna [{layer,lat,lon,name,time(ms|null),sub,key}]
  function entitiesOf(id, data) {
    const out = [];
    if (!data) return out;
    const add = (lat, lon, name, time, sub, key) => {
      if (lat == null || lon == null || !isFinite(lat) || !isFinite(lon)) return;
      out.push({ layer: id, lat: lat, lon: lon, name: name,
                 time: time || null, sub: sub || "", key: key || null });
    };
    const feats = data.features || [];
    switch (id) {
      case "quakes":
        feats.forEach(f => { const c = f.geometry && f.geometry.coordinates;
          if (c) { const p = f.properties;
            add(c[1], c[0], "M " + (p.mag || "?") + " " + (p.place || ""),
                p.time, (p.mag != null ? p.mag + " Mw" : "")); } }); break;
      case "volcano":
        feats.forEach(f => { const c = f.geometry && f.geometry.coordinates;
          if (c) add(c[1], c[0], f.properties.name || "Vulcano", null,
                     f.properties.country || ""); }); break;
      case "fires":
        feats.forEach(f => { const c = f.geometry && f.geometry.coordinates;
          if (c) add(c[1], c[0], f.properties.name || "Incendio",
                     f.properties.date ? Date.parse(f.properties.date) : null, ""); }); break;
      case "cameras":
        feats.forEach(f => { const c = f.geometry && f.geometry.coordinates;
          if (c) add(c[1], c[0], f.properties.title || "Telecamera", null,
                     f.properties.network || ""); }); break;
      case "ships":
        feats.forEach(f => { const c = f.geometry && f.geometry.coordinates;
          if (c) { const p = f.properties, mmsi = String(p.mmsi || "");
            add(c[1], c[0], p.name || ("Nave " + mmsi),
                p.timestamp ? p.timestamp * 1000 : (p.time || null),
                "MMSI " + mmsi + (p.destination ? " -> " + p.destination : ""), mmsi); } }); break;
      case "flights":
        (data.states || []).forEach(s => {
          add(s[6], s[5], "Volo " + ((s[1] || "").trim() || "?"),
              (s[3] || s[4]) ? (s[3] || s[4]) * 1000 : null, s[2] || "", s[0]); }); break;
      case "iss":
        if (data.latitude != null)
          add(data.latitude, data.longitude, "ISS",
              data.timestamp ? data.timestamp * 1000 : null, "stazione spaziale", "iss");
        break;
    }
    return out;
  }

  // Raccoglie le entita' di TUTTI i layer dall'ultima cache in IndexedDB
  // (indipendentemente dal fatto che il layer sia acceso: l'incrocio lavora
  // sull'ultimo stato noto). I satelliti si calcolano a parte, live.
  async function gatherEntities() {
    const ids = ["quakes", "volcano", "fires", "flights", "ships", "iss", "cameras"];
    const all = [];
    for (const id of ids) {
      try { const rec = await dbGet(id);
        if (rec && rec.data) all.push(...entitiesOf(id, rec.data));
      } catch (e) { /* cache assente: salta */ }
    }
    if (photoEntities.length) all.push(...photoEntities);   // foto EXIF geolocalizzate
    return all;
  }

  // Satelliti la cui verticale (ground track) ricade entro raggio dal punto:
  // "chi sta sorvolando adesso". Calcolo client dai TLE gia' caricati.
  function satsNear(focus, radiusKm) {
    const out = [];
    if (!window.satellite || !satRecs.length) return out;
    const now = new Date(), gmst = satellite.gstime(now);
    for (const s of satRecs) {
      let pv; try { pv = satellite.propagate(s.satrec, now); } catch (e) { continue; }
      const pos = pv && pv.position; if (!pos) continue;
      const gd = satellite.eciToGeodetic(pos, gmst);
      const lat = satellite.degreesLat(gd.latitude), lon = satellite.degreesLong(gd.longitude);
      if (!isFinite(lat) || !isFinite(lon)) continue;
      const d = haversine(focus, { lat: lat, lon: lon });
      if (d <= radiusKm) out.push({ name: s.name, group: s.group,
        lat: lat, lon: lon, height: gd.height, dist: d, satnum: s.satrec.satnum });
    }
    out.sort((a, b) => a.dist - b.dist);
    return out;
  }

  // --- Stato + livello grafico dedicato --------------------------------------
  const corrLayer = L.layerGroup().addTo(map);
  let lastResult = null;                 // per dossier/export
  const photoEntities = [];              // foto EXIF con GPS (riempito da img-intel)

  // Storico: due livelli SEPARATI. histLayer = riavvolgimento di una scia gia'
  // registrata (si spegne chiudendo l'hub). analysisLayer = dati importati e
  // "affiancati" per un'analisi a parte: NON tocca il DB ne' i feed live e resta
  // acceso finche' non lo si rimuove, cosi' la piattaforma continua a lavorare.
  const histLayer = L.layerGroup();
  const analysisLayer = L.layerGroup();
  let scrub = null;                      // stato del cursore di riavvolgimento
  let analysisData = null;               // ultimo backup affiancato (in memoria)

  // --- Pannello --------------------------------------------------------------
  const el = document.getElementById("correlate");
  const body = document.getElementById("corr-body");
  const qIn = document.getElementById("corr-q");
  function radiusVal() { return parseInt(document.getElementById("corr-radius").value, 10) || 100; }
  function windowVal() { return parseInt(document.getElementById("corr-window").value, 10) || 0; }

  function openHub() { el.hidden = false; }
  function closeHub() {
    el.hidden = true;
    corrLayer.clearLayers();      // via l'area/i marcatori disegnati
    stopTrace();
    stopScrub();                  // ferma il riavvolgimento e spegne histLayer
    // NB: analysisLayer (dati affiancati) resta acceso di proposito.
    // annulla eventuali modalita' armate e ripristina il cursore
    corrDrawing = false; corrStart = null; pointArm = false;
    if (corrRubber) { map.removeLayer(corrRubber); corrRubber = null; }
    map.dragging.enable();
    map.getContainer().style.cursor = "";
  }

  // --- Rendering dei risultati ----------------------------------------------
  function fmtTime(t) { try { return t ? new Date(t).toLocaleString() : ""; } catch (e) { return ""; } }
  function grp(hits) {
    const g = {};
    hits.forEach(h => { (g[h.layer] = g[h.layer] || []).push(h); });
    return g;
  }
  function itemRow(h, withDist) {
    const dist = (withDist && h.dist != null) ? h.dist.toFixed(1) + " km" : "";
    const meta = [h.sub, fmtTime(h.time), dist].filter(Boolean).join(" · ");
    return '<div class="corr-item" data-lat="' + h.lat + '" data-lon="' + h.lon + '">' +
      '<span class="ci-dot" style="background:' + (LAYER_COLOR[h.layer] || "#888") + '"></span>' +
      '<span class="ci-txt"><b>' + esc(h.name) + "</b>" +
      (meta ? '<span class="ci-meta">' + esc(meta) + "</span>" : "") + "</span>" +
      (canTrace(h) ? '<button class="ci-trace" title="Traccia il percorso">scia</button>' : "") +
      "</div>";
  }
  function canTrace(h) { return (h.layer === "ships" || h.layer === "flights" || h.layer === "iss") && h.key; }

  function renderResults(res) {
    lastResult = res;
    corrLayer.clearLayers();
    // Contesto grafico: cerchio/area del fuoco + marcatori dei risultati
    if (res.mode === "point") {
      L.circle([res.focus.lat, res.focus.lon], { radius: res.radiusKm * 1000,
        color: "#00e5ff", weight: 1, fill: false, dashArray: "4" }).addTo(corrLayer);
      L.circleMarker([res.focus.lat, res.focus.lon],
        { radius: 6, color: "#00e5ff", weight: 2, fillOpacity: 0.9 })
        .bindPopup("Punto di correlazione").addTo(corrLayer);
    } else if (res.mode === "area") {
      L.rectangle(res.bounds, { color: "#00e5ff", weight: 1, fill: false }).addTo(corrLayer);
    }
    res.hits.forEach(h => {
      L.circleMarker([h.lat, h.lon], dot(LAYER_COLOR[h.layer] || "#888", 4))
        .bindPopup(popup(h.name, [["Layer", LAYER_NAME[h.layer] || h.layer],
          ["Quando", fmtTime(h.time)], ["Info", h.sub]])).addTo(corrLayer);
    });

    const g = grp(res.hits);
    const order = ["ships", "flights", "iss", "photo", "quakes", "fires", "volcano", "cameras"];
    let h = '<div class="corr-summary">';
    const focusTxt = res.mode === "area" ? "Area selezionata"
      : ("Punto " + res.focus.lat.toFixed(3) + ", " + res.focus.lon.toFixed(3) +
         " · raggio " + res.radiusKm + " km");
    h += "<b>" + esc(res.title || focusTxt) + "</b><span>" + res.hits.length +
      " elementi correlati" + (res.winH ? " · ultime " + res.winH + "h" : "") + "</span></div>";

    order.forEach(id => {
      const arr = g[id]; if (!arr || !arr.length) return;
      arr.sort((a, b) => (a.dist || 0) - (b.dist || 0));
      h += '<div class="corr-grp"><div class="cg-head"><span class="cg-sw" style="background:' +
        (LAYER_COLOR[id] || "#888") + '"></span>' + (LAYER_NAME[id] || id) +
        ' <span class="cg-n">' + arr.length + "</span></div>";
      arr.slice(0, 60).forEach(it => { h += itemRow(it, res.mode === "point"); });
      if (arr.length > 60) h += '<div class="corr-more">+ altri ' + (arr.length - 60) + "</div>";
      h += "</div>";
    });

    // Satelliti che stanno sorvolando
    if (res.sats && res.sats.length) {
      h += '<div class="corr-grp"><div class="cg-head"><span class="cg-sw" style="background:' +
        LAYER_COLOR.satellites + '"></span>Satelliti in transito <span class="cg-n">' +
        res.sats.length + "</span></div>";
      res.sats.slice(0, 40).forEach(s => {
        L.circleMarker([s.lat, s.lon], dot(LAYER_COLOR.satellites, 4))
          .bindPopup(popup(s.name, [["Categoria", GROUP_IT[s.group] || s.group],
            ["Quota", s.height.toFixed(0) + " km"], ["Distanza verticale", s.dist.toFixed(1) + " km"]]))
          .addTo(corrLayer);
        h += '<div class="corr-item" data-lat="' + s.lat + '" data-lon="' + s.lon + '">' +
          '<span class="ci-dot" style="background:' + LAYER_COLOR.satellites + '"></span>' +
          '<span class="ci-txt"><b>' + esc(s.name) + "</b><span class=\"ci-meta\">" +
          esc((GROUP_IT[s.group] || s.group) + " · " + s.height.toFixed(0) + " km · a " +
              s.dist.toFixed(0) + " km") + "</span></span></div>";
      });
      h += "</div>";
    }
    if (!res.hits.length && !(res.sats && res.sats.length))
      h += '<p class="corr-empty">Nessuna correlazione. Accendi piu’ layer o allarga raggio/finestra.</p>';
    body.innerHTML = h;
  }

  // --- Correlazione: PUNTO ---------------------------------------------------
  async function correlatePoint(focus, title) {
    openHub();
    body.innerHTML = '<p class="corr-empty">Incrocio in corso…</p>';
    const radiusKm = radiusVal(), winH = windowVal();
    const all = await gatherEntities();
    const now = Date.now();
    const hits = [];
    all.forEach(e => {
      const d = haversine(focus, e); if (d > radiusKm) return;
      if (winH > 0 && e.time && now - e.time > winH * 3600000) return;
      e.dist = d; hits.push(e);
    });
    const sats = satsNear(focus, radiusKm);
    renderResults({ mode: "point", focus: focus, radiusKm: radiusKm, winH: winH,
      hits: hits, sats: sats, title: title });
  }

  // --- Correlazione: AREA ----------------------------------------------------
  async function correlateArea(bounds) {
    openHub();
    body.innerHTML = '<p class="corr-empty">Incrocio in corso…</p>';
    const winH = windowVal(), now = Date.now();
    const all = await gatherEntities();
    const hits = all.filter(e => bounds.contains([e.lat, e.lon]) &&
      !(winH > 0 && e.time && now - e.time > winH * 3600000));
    hits.forEach(e => { e.dist = null; });
    // Satelliti la cui verticale cade DENTRO il riquadro
    const sats = [];
    if (window.satellite && satRecs.length) {
      const nowd = new Date(), gmst = satellite.gstime(nowd);
      for (const s of satRecs) {
        let pv; try { pv = satellite.propagate(s.satrec, nowd); } catch (e) { continue; }
        const pos = pv && pv.position; if (!pos) continue;
        const gd = satellite.eciToGeodetic(pos, gmst);
        const lat = satellite.degreesLat(gd.latitude), lon = satellite.degreesLong(gd.longitude);
        if (isFinite(lat) && isFinite(lon) && bounds.contains([lat, lon]))
          sats.push({ name: s.name, group: s.group, lat: lat, lon: lon,
            height: gd.height, dist: 0, satnum: s.satrec.satnum });
      }
    }
    renderResults({ mode: "area", bounds: bounds, winH: winH, hits: hits, sats: sats });
  }

  // --- Ricerca ENTITA' (nave/volo/satellite) ---------------------------------
  async function searchEntity(q) {
    q = (q || "").trim().toLowerCase();
    if (!q) return;
    openHub();
    body.innerHTML = '<p class="corr-empty">Ricerca…</p>';
    const res = [];
    try { const sh = await dbGet("ships");
      if (sh && sh.data) (sh.data.features || []).forEach(f => {
        const p = f.properties, c = f.geometry && f.geometry.coordinates; if (!c) return;
        const name = (p.name || "").toLowerCase(), mmsi = String(p.mmsi || "");
        if (name.includes(q) || mmsi.includes(q))
          res.push({ layer: "ships", name: p.name || ("Nave " + mmsi),
            lat: c[1], lon: c[0], key: mmsi, sub: "MMSI " + mmsi });
      });
    } catch (e) {}
    try { const fl = await dbGet("flights");
      if (fl && fl.data) (fl.data.states || []).forEach(s => {
        const cs = (s[1] || "").trim().toLowerCase(), ic = (s[0] || "").toLowerCase();
        if ((cs && cs.includes(q)) || ic.includes(q)) {
          if (s[6] != null) res.push({ layer: "flights", name: "Volo " + ((s[1] || "").trim() || "?"),
            lat: s[6], lon: s[5], key: s[0], sub: (s[2] || "") + " · " + (s[0] || "") });
        }
      });
    } catch (e) {}
    if (window.satellite) satRecs.forEach(s => {
      if ((s.name || "").toLowerCase().includes(q))
        res.push({ layer: "satellites", name: s.name, sat: s, sub: GROUP_IT[s.group] || s.group });
    });

    let h = '<div class="corr-summary"><b>Ricerca "' + esc(q) + '"</b><span>' +
      res.length + " risultati</span></div>";
    if (!res.length) h += '<p class="corr-empty">Nessuna entita’. Il layer relativo dev’essere stato caricato almeno una volta.</p>';
    res.slice(0, 60).forEach((r, i) => {
      h += '<div class="corr-item corr-hit" data-idx="' + i + '">' +
        '<span class="ci-dot" style="background:' + (LAYER_COLOR[r.layer] || "#888") + '"></span>' +
        '<span class="ci-txt"><b>' + esc(r.name) + "</b><span class=\"ci-meta\">" +
        esc((LAYER_NAME[r.layer] || r.layer) + (r.sub ? " · " + r.sub : "")) + "</span></span>" +
        (canTrace(r) ? '<button class="ci-trace" title="Traccia">scia</button>' : "") + "</div>";
    });
    body.innerHTML = h;
    searchResults = res.slice(0, 60);
  }
  let searchResults = [];

  function focusEntity(r) {
    let lat = r.lat, lon = r.lon;
    if (r.layer === "satellites" && r.sat && window.satellite) {   // posizione live
      const now = new Date();
      let pv; try { pv = satellite.propagate(r.sat.satrec, now); } catch (e) { pv = null; }
      if (pv && pv.position) {
        const gd = satellite.eciToGeodetic(pv.position, satellite.gstime(now));
        lat = satellite.degreesLat(gd.latitude); lon = satellite.degreesLong(gd.longitude);
      }
    }
    if (lat == null || lon == null) return;
    map.flyTo([lat, lon], Math.max(map.getZoom(), 5));
    correlatePoint({ lat: lat, lon: lon }, r.name);
  }

  // --- Tracce (scie) su richiesta -------------------------------------------
  // Campiona la posizione dell'entita' dalla cache che il motore aggiorna, e
  // fa crescere una polilinea. Se il layer non e' acceso, lo accende (serve a
  // tenere aggiornata la cache).
  let trace = null;
  function stopTrace() {
    if (trace) { clearInterval(trace.timer); if (trace.line) corrLayer.removeLayer(trace.line); }
    trace = null;
  }
  async function startTrace(ent) {
    stopTrace();
    if (!hdb) { try { hdb = await openDB(); } catch (e) { /* niente storico */ } }
    if (!active[ent.layer] && typeof toggleFeed === "function") toggleFeed(ent.layer);
    // Riparte dallo storico gia' salvato in IndexedDB: la scia continua tra le
    // sessioni invece di ricominciare da zero a ogni apertura.
    let seed = [];
    try {
      const hist = await histRangeOf(ent.layer, ent.key);
      seed = hist.map(r => [r.lat, r.lon]);
    } catch (e) { /* storico assente */ }
    if (!seed.length && ent.lat != null) seed = [[ent.lat, ent.lon]];
    const line = L.polyline(seed, { color: LAYER_COLOR[ent.layer] || "#00e5ff",
      weight: 2, opacity: 0.9 }).addTo(corrLayer);
    trace = { layer: ent.layer, key: ent.key, name: ent.name, line: line,
      pts: seed.slice(), timer: null, lastT: 0 };
    // In background: registra l'entita' nel recorder, cosi' continua a essere
    // campionata anche a finestra chiusa (il salvataggio lo fa il recorder).
    if (isServerTrack()) serverFollow(ent.layer, ent.key, ent.name, "add");
    const sample = async () => {
      try {
        const rec = await dbGet(ent.layer); if (!rec || !rec.data) return;
        let pos = null, t = rec.ts || Date.now();
        if (ent.layer === "ships") (rec.data.features || []).some(f => {
          if (String((f.properties || {}).mmsi || "") === ent.key) {
            const c = f.geometry.coordinates; pos = [c[1], c[0]]; return true; } return false; });
        else if (ent.layer === "flights") (rec.data.states || []).some(s => {
          if ((s[0] || "") === ent.key) { if (s[6] != null) pos = [s[6], s[5]]; return true; } return false; });
        else if (ent.layer === "iss") { if (rec.data.latitude != null) {
          pos = [rec.data.latitude, rec.data.longitude];
          if (rec.data.timestamp) t = rec.data.timestamp * 1000; } }
        if (pos) {
          trace.pts.push(pos); trace.line.setLatLngs(trace.pts);
          // persiste solo se il campione e' "nuovo" (evita doppioni su cache ferma).
          // In modo "server" NON scrive qui: il recorder di background persiste
          // su SQLite (anche a finestra chiusa); qui resta solo la linea viva.
          if (t > trace.lastT && !isServerTrack()) {
            trace.lastT = t;
            await trackPut({ layer: ent.layer, key: ent.key, lat: pos[0], lon: pos[1],
              t: t, name: ent.name });
            trackPrune(ent.layer, ent.key);
          }
        }
      } catch (e) { /* salta un campione */ }
    };
    sample();
    trace.timer = setInterval(sample, 12000);
    const note = document.getElementById("corr-tracenote");
    if (note) { note.textContent = "Traccia attiva: " + ent.name +
      (isServerTrack() ? " (registro in background su file, anche a finestra chiusa)"
                       : " (campiono ogni 12s, salvo lo storico nel browser)");
      note.hidden = false; }
  }

  // --- ISS: campionamento sempre attivo dello storico ------------------------
  // L'ISS e' un solo punto: la registriamo di continuo (fetch diretto del feed
  // ogni 60s) cosi' lo storico c'e' anche senza attivare la scia. Solo mentre
  // HORUS e' aperto (per scelta: tutto in locale, niente daemon lato server).
  let issLastT = 0;
  async function sampleISS() {
    try {
      // In background lo storico ISS lo tiene il recorder (SQLite): qui niente.
      if (typeof trackMode === "function" && trackMode() === "server") return;
      if (!hdb) { try { hdb = await openDB(); } catch (e) { return; } }
      const r = await fetch("api/feed/iss");
      if (!r.ok) return;
      const d = await r.json();
      if (d.latitude == null) return;
      const t = d.timestamp ? d.timestamp * 1000 : Date.now();
      if (t <= issLastT) return;
      issLastT = t;
      await trackPut({ layer: "iss", key: "iss", lat: d.latitude, lon: d.longitude,
        t: t, name: "ISS" });
      trackPrune("iss", "iss");
    } catch (e) { /* rete assente: riprova al giro dopo */ }
  }
  setTimeout(function () { if (typeof trackPut === "function") {
    sampleISS(); setInterval(sampleISS, 60000); } }, 4000);

  // --- Storico scie: riavvolgi, backup, ripristino ---------------------------
  // Tutto client-side (IndexedDB). Il pannello vive dentro #corr-body come gli
  // altri strumenti; lo stato grafico (histLayer/analysisLayer/scrub) sta piu'
  // in alto cosi' sopravvive a un re-render del corpo.
  const HIST_LAYER_IT = { ships: "Navi", flights: "Voli", iss: "ISS" };
  let histRows = [];   // righe entita' correnti (indicizzate dalla <select>)

  // Sorgente dati dello storico: "server" = recorder di background su SQLite
  // (via API); "local" = IndexedDB nel browser (solo a finestra aperta). Il
  // pannello Storico e le scie leggono/scrivono dalla sorgente giusta.
  function isServerTrack() { return typeof trackMode === "function" && trackMode() === "server"; }
  async function histEntities() {
    if (isServerTrack()) {
      try { return (await (await fetch("api/track/entities")).json()).entities || []; }
      catch (e) { return []; }
    }
    return await trackEntities();
  }
  async function histRangeOf(layer, key) {
    if (isServerTrack()) {
      try {
        const u = "api/track/range?layer=" + encodeURIComponent(layer) +
          "&key=" + encodeURIComponent(key);
        return (await (await fetch(u)).json()).samples || [];
      } catch (e) { return []; }
    }
    return await trackRange(layer, key, 0, null);
  }
  async function histExport() {
    if (isServerTrack()) {
      try { return await (await fetch("api/track/export")).json(); } catch (e) { return null; }
    }
    return await trackExportAll();
  }
  async function histImport(samples) {
    if (isServerTrack()) {
      try {
        const d = await (await fetch("api/track/import", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ samples: samples }) })).json();
        return d.imported || 0;
      } catch (e) { return 0; }
    }
    return await trackImportMerge(samples);
  }
  // Registra un'entita' da seguire nel recorder di background (solo modo server).
  async function serverFollow(layer, key, name, op) {
    if (!isServerTrack()) return;
    try {
      await fetch("api/recorder/follow", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ layer: layer, key: String(key), name: name || "", op: op || "add" }) });
    } catch (e) { /* recorder non raggiungibile */ }
  }

  function stopScrub() {
    if (scrub && scrub.timer) clearInterval(scrub.timer);
    scrub = null;
    histLayer.clearLayers();
    if (map.hasLayer(histLayer)) map.removeLayer(histLayer);
    const pl = document.getElementById("ch-play");
    if (pl) pl.textContent = "▶";
  }

  function histLabel(m) {
    const g = HIST_LAYER_IT[m.layer] || m.layer;
    const nm = m.name || m.key;
    const n = m.count || 0;
    const span = m.first && m.last ? fmtTime(m.first) + " → " + fmtTime(m.last) : "";
    return g + ": " + nm + "  (" + n + " punti" + (span ? ", " + span : "") + ")";
  }

  async function refreshHistEntities() {
    const sel = document.getElementById("ch-ent");
    if (!sel) return;
    histRows = await histEntities();
    histRows.sort((a, b) => (b.last || 0) - (a.last || 0));
    if (!histRows.length) {
      sel.innerHTML = '<option value="">— nessuno storico ancora —</option>';
    } else {
      sel.innerHTML = '<option value="">— scegli —</option>' +
        histRows.map((m, i) => '<option value="' + i + '">' + esc(histLabel(m)) + "</option>").join("");
    }
    const player = document.getElementById("ch-player");
    if (player) player.hidden = true;
    stopScrub();
  }

  async function loadHistEntity(i) {
    stopScrub();
    const m = histRows[i];
    if (!m) return;
    const rows = await histRangeOf(m.layer, m.key);
    const pts = rows.map(r => [r.lat, r.lon]);
    if (!pts.length) return;
    histLayer.addTo(map);
    const col = LAYER_COLOR[m.layer] || "#00e5ff";
    // scia completa (tenue) + cursore che avanza
    L.polyline(pts, { color: col, weight: 1, opacity: 0.35, dashArray: "3" }).addTo(histLayer);
    const cursor = L.circleMarker(pts[0], { radius: 6, color: col, weight: 2, fillOpacity: 0.9 }).addTo(histLayer);
    const done = L.polyline([pts[0]], { color: col, weight: 3, opacity: 0.95 }).addTo(histLayer);
    scrub = { rows: rows, pts: pts, cursor: cursor, done: done, i: 0, timer: null };
    const range = document.getElementById("ch-range");
    const player = document.getElementById("ch-player");
    if (range) { range.max = String(pts.length - 1); range.value = "0"; }
    if (player) player.hidden = false;
    setScrubIndex(0);
    map.flyToBounds(L.latLngBounds(pts), { maxZoom: 8, padding: [40, 40] });
  }

  function setScrubIndex(i) {
    if (!scrub) return;
    i = Math.max(0, Math.min(i, scrub.pts.length - 1));
    scrub.i = i;
    scrub.cursor.setLatLng(scrub.pts[i]);
    scrub.done.setLatLngs(scrub.pts.slice(0, i + 1));
    const range = document.getElementById("ch-range");
    const time = document.getElementById("ch-time");
    if (range) range.value = String(i);
    if (time) time.textContent = fmtTime(scrub.rows[i].t) + "  (" + (i + 1) + "/" + scrub.pts.length + ")";
  }

  function togglePlay() {
    if (!scrub) return;
    const pl = document.getElementById("ch-play");
    if (scrub.timer) {
      clearInterval(scrub.timer); scrub.timer = null;
      if (pl) pl.textContent = "▶";
      return;
    }
    if (scrub.i >= scrub.pts.length - 1) setScrubIndex(0);
    if (pl) pl.textContent = "⏸";
    scrub.timer = setInterval(() => {
      if (!scrub) return;
      if (scrub.i >= scrub.pts.length - 1) { togglePlay(); return; }
      setScrubIndex(scrub.i + 1);
    }, 400);
  }

  async function doBackup() {
    const note = document.getElementById("ch-note");
    const data = await histExport();
    if (!data || !data.samples.length) {
      if (note) note.textContent = "Nessuno storico da salvare.";
      return;
    }
    const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    a.href = url; a.download = "horus-storico-" + stamp + ".json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    if (note) note.textContent = "Backup salvato: " + data.samples.length + " campioni.";
  }

  // Ripristino: chiede se FONDERE nel DB vivo o AFFIANCARE per analisi separata.
  function askRestore(parsed) {
    const box = document.getElementById("ch-analysis");
    const note = document.getElementById("ch-note");
    const samples = (parsed && parsed.samples) || [];
    if (!samples.length) { if (note) note.textContent = "File vuoto o non valido."; return; }
    const ents = {}; samples.forEach(s => { ents[s.layer + "|" + s.key] = true; });
    box.innerHTML =
      '<div class="ch-choice">' +
        '<p>Backup: <b>' + samples.length + '</b> campioni, <b>' +
          Object.keys(ents).length + '</b> entità.</p>' +
        '<div class="ch-choice-btns">' +
          '<button id="ch-do-merge" class="corr-btn">Ripristina nel DB</button>' +
          '<button id="ch-do-side" class="corr-btn">Affianca (analisi separata)</button>' +
        '</div>' +
        '<p class="corr-note">«Ripristina» fonde i dati nello storico vivo (rispetta la ' +
        'finestra di ore impostata). «Affianca» li mostra solo in mappa, senza toccare ' +
        'il DB né i feed: la piattaforma continua a lavorare normalmente.</p>' +
      "</div>";
    document.getElementById("ch-do-merge").addEventListener("click", async () => {
      box.innerHTML = '<p class="corr-note">Ripristino in corso…</p>';
      const n = await histImport(samples);
      if (note) note.textContent = "Ripristinati " + n + " campioni nello storico" +
        (isServerTrack() ? " (SQLite di background)." : ".");
      box.innerHTML = "";
      await refreshHistEntities();
    });
    document.getElementById("ch-do-side").addEventListener("click", () => {
      showSideBySide(samples);
      box.innerHTML =
        '<div class="ch-analysis-on">' +
          '<span>Analisi affiancata attiva (' + samples.length + ' campioni).</span>' +
          '<button id="ch-side-clear" class="corr-btn">Rimuovi</button>' +
        "</div>";
      document.getElementById("ch-side-clear").addEventListener("click", clearSideBySide);
      if (note) note.textContent = "Dati affiancati in mappa (arancio tratteggiato). Non toccano il DB.";
    });
  }

  // Disegna i campioni importati su analysisLayer, raggruppati per entita'.
  // Colore fisso distinto dai layer live, tratteggiato: si riconoscono a colpo.
  function showSideBySide(samples) {
    clearSideBySide();
    analysisData = samples;
    const groups = {};
    samples.forEach(s => {
      if (s.lat == null || s.lon == null) return;
      (groups[s.layer + "|" + s.key] = groups[s.layer + "|" + s.key] || []).push(s);
    });
    const all = [];
    Object.keys(groups).forEach(k => {
      const g = groups[k].slice().sort((a, b) => (a.t || 0) - (b.t || 0));
      const pts = g.map(s => [s.lat, s.lon]);
      all.push(...pts);
      L.polyline(pts, { color: "#ffb000", weight: 2, opacity: 0.9, dashArray: "6 4" }).addTo(analysisLayer);
      const last = g[g.length - 1];
      L.circleMarker(pts[pts.length - 1], { radius: 5, color: "#ffb000", weight: 2, fillOpacity: 0.85 })
        .bindPopup("Analisi affiancata · " + esc(last.name || last.key)).addTo(analysisLayer);
    });
    analysisLayer.addTo(map);
    if (all.length) map.flyToBounds(L.latLngBounds(all), { maxZoom: 7, padding: [40, 40] });
  }
  function clearSideBySide() {
    analysisLayer.clearLayers();
    if (map.hasLayer(analysisLayer)) map.removeLayer(analysisLayer);
    analysisData = null;
    const box = document.getElementById("ch-analysis");
    if (box) box.innerHTML = "";
    const note = document.getElementById("ch-note");
    if (note) note.textContent = "Analisi affiancata rimossa.";
  }

  function histModeNote() {
    return isServerTrack()
      ? "Registrazione in BACKGROUND su file (anche a finestra chiusa): entità seguite + ISS. Cambi la modalità dalle Impostazioni."
      : "Registro solo mentre HORUS è aperto (nel browser): entità con scia attiva + ISS.";
  }
  function openHist() {
    openHub();
    stopScrub();
    const cur = (typeof trackRetentionHours === "function") ? trackRetentionHours() : 72;
    const hopts = [["6", "6 ore"], ["12", "12 ore"], ["24", "24 ore"], ["72", "3 giorni"],
      ["168", "7 giorni"], ["0", "illimitato"]];
    body.innerHTML =
      '<div class="ch-panel">' +
        '<div class="ch-row">' +
          '<label class="ch-lbl">Ore da registrare' +
            '<select id="ch-hours">' +
              hopts.map(o => '<option value="' + o[0] + '"' +
                (parseInt(o[0], 10) === cur ? " selected" : "") + ">" + o[1] + "</option>").join("") +
            "</select></label>" +
          '<button id="ch-refresh" class="corr-btn" title="Ricarica l\'elenco">Aggiorna</button>' +
        "</div>" +
        '<label class="ch-lbl">Entità registrata<select id="ch-ent"></select></label>' +
        '<div id="ch-player" hidden>' +
          '<input id="ch-range" type="range" min="0" max="0" value="0">' +
          '<div class="ch-pl-row">' +
            '<button id="ch-play" class="corr-btn">▶</button>' +
            '<span id="ch-time" class="ch-time"></span>' +
          "</div>" +
        "</div>" +
        '<div class="ch-io">' +
          '<button id="ch-backup" class="corr-btn">Salva backup</button>' +
          '<button id="ch-restore" class="corr-btn">Ripristina&hellip;</button>' +
          '<input id="ch-file" type="file" accept="application/json,.json" hidden>' +
        "</div>" +
        '<div id="ch-analysis"></div>' +
        '<p id="ch-note" class="corr-note">' + esc(histModeNote()) + "</p>" +
      "</div>";
    document.getElementById("ch-hours").addEventListener("change", e => {
      const h = parseInt(e.target.value, 10) || 0;
      setTrackRetentionHours(h);
      const note = document.getElementById("ch-note");
      if (note) note.textContent = h ? ("Registro le ultime " + h + " ore.") : "Registrazione illimitata (solo per numero di punti).";
    });
    document.getElementById("ch-refresh").addEventListener("click", refreshHistEntities);
    document.getElementById("ch-ent").addEventListener("change", e => {
      const v = e.target.value; if (v === "") { stopScrub();
        const p = document.getElementById("ch-player"); if (p) p.hidden = true; return; }
      loadHistEntity(+v);
    });
    document.getElementById("ch-range").addEventListener("input", e => setScrubIndex(+e.target.value));
    document.getElementById("ch-play").addEventListener("click", togglePlay);
    document.getElementById("ch-backup").addEventListener("click", doBackup);
    const file = document.getElementById("ch-file");
    document.getElementById("ch-restore").addEventListener("click", () => file.click());
    file.addEventListener("change", async () => {
      const f = file.files && file.files[0]; file.value = "";
      if (!f) return;
      try {
        const parsed = JSON.parse(await f.text());
        askRestore(parsed);
      } catch (e) {
        const note = document.getElementById("ch-note");
        if (note) note.textContent = "File non leggibile: " + (e.message || e);
      }
    });
    // se c'e' un'analisi affiancata gia' attiva, ricordo che c'e'
    if (analysisData) {
      document.getElementById("ch-analysis").innerHTML =
        '<div class="ch-analysis-on"><span>Analisi affiancata attiva (' +
        analysisData.length + ' campioni).</span>' +
        '<button id="ch-side-clear" class="corr-btn">Rimuovi</button></div>';
      document.getElementById("ch-side-clear").addEventListener("click", clearSideBySide);
    }
    refreshHistEntities();
  }

  // --- Dossier + export ------------------------------------------------------
  function toDossier() {
    if (!lastResult) return;
    const r = lastResult, lines = [];
    lines.push(r.mode === "area" ? "Correlazione area" :
      ("Correlazione punto " + r.focus.lat.toFixed(4) + ", " + r.focus.lon.toFixed(4) +
       " (raggio " + r.radiusKm + " km)"));
    if (r.winH) lines.push("Finestra: ultime " + r.winH + "h");
    const g = grp(r.hits);
    Object.keys(g).forEach(id => lines.push((LAYER_NAME[id] || id) + ": " + g[id].length));
    if (r.sats && r.sats.length) lines.push("Satelliti in transito: " + r.sats.length);
    r.hits.slice(0, 40).forEach(h => lines.push("  - [" + (LAYER_NAME[h.layer] || h.layer) + "] " +
      h.name + (h.dist != null ? " (" + h.dist.toFixed(1) + " km)" : "") +
      (h.time ? " " + fmtTime(h.time) : "")));
    addDossier("correlazione", r.title || (r.mode === "area" ? "Area" : "Punto"), lines.join("\n"));
    const note = document.getElementById("corr-note");
    if (note) note.textContent = "Aggiunto al dossier (tab Report).";
  }
  function exportGeoJSON() {
    if (!lastResult) return;
    const fc = { type: "FeatureCollection", features: [] };
    lastResult.hits.forEach(h => fc.features.push({ type: "Feature",
      geometry: { type: "Point", coordinates: [h.lon, h.lat] },
      properties: { layer: h.layer, name: h.name, time: h.time, info: h.sub,
        dist_km: h.dist != null ? +h.dist.toFixed(2) : null } }));
    (lastResult.sats || []).forEach(s => fc.features.push({ type: "Feature",
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: { layer: "satellites", name: s.name, height_km: +s.height.toFixed(0) } }));
    try {
      const blob = new Blob([JSON.stringify(fc, null, 2)], { type: "application/geo+json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "horus-correlazione-" + Date.now() + ".geojson";
      document.body.appendChild(a); a.click(); a.remove();
      const note = document.getElementById("corr-note");
      if (note) note.textContent = fc.features.length + " elementi esportati in GeoJSON.";
    } catch (e) {
      const note = document.getElementById("corr-note");
      if (note) note.textContent = "Export non riuscito: " + (e.message || e);
    }
  }

  // --- Disegno del riquadro per la modalita' Area ----------------------------
  let corrDrawing = false, corrStart = null, corrRubber = null;
  function beginAreaDraw() {
    corrDrawing = true;
    map.dragging.disable();
    map.getContainer().style.cursor = "crosshair";
    const note = document.getElementById("corr-note");
    if (note) note.textContent = "Trascina sulla mappa per selezionare l'area.";
  }
  map.on("mousedown", e => {
    if (!corrDrawing) return;
    corrStart = e.latlng;
    corrRubber = L.rectangle([corrStart, corrStart],
      { color: "#00e5ff", weight: 1, dashArray: "4", fillOpacity: 0.05 }).addTo(map);
  });
  map.on("mousemove", e => {
    if (corrDrawing && corrStart && corrRubber)
      corrRubber.setBounds(L.latLngBounds(corrStart, e.latlng));
  });
  map.on("mouseup", e => {
    if (!corrDrawing || !corrStart) return;
    const b = L.latLngBounds(corrStart, e.latlng);
    corrDrawing = false; corrStart = null;
    map.dragging.enable(); map.getContainer().style.cursor = "";
    if (corrRubber) { map.removeLayer(corrRubber); corrRubber = null; }
    correlateArea(b);
  });

  // --- Modalita' Punto: il prossimo clic sulla mappa fissa il fuoco ----------
  let pointArm = false;
  function armPoint() {
    pointArm = true;
    map.getContainer().style.cursor = "crosshair";
    const note = document.getElementById("corr-note");
    if (note) note.textContent = "Clic sulla mappa per fissare il punto di correlazione.";
  }
  map.on("click", e => {
    if (!pointArm) return;
    pointArm = false; map.getContainer().style.cursor = "";
    correlatePoint({ lat: e.latlng.lat, lon: e.latlng.lng });
  });

  // --- Aggancio EXIF: una foto geolocalizzata diventa un punto correlabile ---
  // Chiamata da img-intel.js quando estrae GPS da una foto.
  window.HORUS_addPhoto = function (lat, lon, name, time) {
    const p = { layer: "photo", lat: lat, lon: lon, name: name || "Foto",
      time: time || null, sub: "EXIF GPS", key: null };
    photoEntities.push(p);
    map.flyTo([lat, lon], 8);
    correlatePoint({ lat: lat, lon: lon }, name || "Foto (EXIF)");
  };
  window.HORUS_openCorrelate = openHub;

  // --- Wiring UI -------------------------------------------------------------
  const bind = (id, ev, fn) => { const n = document.getElementById(id); if (n) n.addEventListener(ev, fn); };
  bind("corr-open", "click", openHub);
  bind("corr-close", "click", closeHub);
  bind("corr-expand", "click", () => el.classList.toggle("expanded"));
  bind("corr-area", "click", beginAreaDraw);
  bind("corr-point", "click", armPoint);
  bind("corr-hist-btn", "click", openHist);
  bind("corr-search", "click", () => searchEntity(qIn.value));
  bind("corr-dossier", "click", toDossier);
  bind("corr-export", "click", exportGeoJSON);
  bind("corr-tracestop", "click", () => {
    stopTrace();
    const note = document.getElementById("corr-tracenote"); if (note) note.hidden = true;
  });
  if (qIn) qIn.addEventListener("keydown", e => { if (e.key === "Enter") searchEntity(qIn.value); });

  // Cambiare raggio/finestra rilancia SUBITO l'ultimo incrocio con i nuovi
  // valori: senza questo la combo sembrava non avere effetto (il raggio si
  // leggeva solo al momento della selezione del punto/area).
  function rerunLast() {
    if (el.hidden || !lastResult) return;
    if (lastResult.mode === "point")
      correlatePoint(lastResult.focus, lastResult.title);
    else if (lastResult.mode === "area" && lastResult.bounds)
      correlateArea(lastResult.bounds);
  }
  bind("corr-radius", "change", rerunLast);
  bind("corr-window", "change", rerunLast);

  // Deleghe sui risultati: clic su una voce -> vai; "scia" -> traccia
  body.addEventListener("click", e => {
    const tr = e.target.closest(".ci-trace");
    if (tr) {
      e.stopPropagation();
      const hit = e.target.closest(".corr-hit");
      if (hit) { const r = searchResults[+hit.dataset.idx]; if (r) startTrace(r); return; }
      // dalle liste di correlazione: ricostruisco l'entita' dal DOM
      const it = e.target.closest(".corr-item");
      if (it && lastResult) {
        const cand = (lastResult.hits || []).find(x =>
          Math.abs(x.lat - +it.dataset.lat) < 1e-6 && Math.abs(x.lon - +it.dataset.lon) < 1e-6);
        if (cand && canTrace(cand)) startTrace(cand);
      }
      return;
    }
    const hit = e.target.closest(".corr-hit");
    if (hit) { const r = searchResults[+hit.dataset.idx]; if (r) focusEntity(r); return; }
    const it = e.target.closest(".corr-item");
    if (it && it.dataset.lat) map.flyTo([+it.dataset.lat, +it.dataset.lon], Math.max(map.getZoom(), 6));
  });
})();
