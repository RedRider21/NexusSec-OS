// graph.js — Grafo relazionale del dossier per HORUS.
//
// Trasforma le voci del dossier (variabile globale `dossier` definita in app.js)
// in un grafo: i NODI sono le entità (la voce stessa più gli identificatori che
// contiene: IP, domini, email, username, ASN, luoghi); gli ARCHI sono i legami
// dedotti. Due voci che condividono lo stesso identificatore restano collegate
// automaticamente perché puntano allo stesso nodo-attributo — è così che si
// "tirano fuori le relazioni". In più: archi di vicinanza geografica e di
// finestra temporale fra le voci.
//
// Nessuna dipendenza esterna: layout force-directed (Fruchterman-Reingold) e
// rendering SVG scritti a mano. Dipende da: `dossier`, `esc`, `makeDraggable`
// (app.js), tutti nello stesso realm (script classici).
(function () {
  "use strict";
  const SVGNS = "http://www.w3.org/2000/svg";
  const W = 960, H = 640;                 // viewBox logico
  const KIND = {
    entry:    { color: "#00e5ff", label: "voce" },
    ip:       { color: "#ff5a8a", label: "IP" },
    domain:   { color: "#7ee0ff", label: "dominio" },
    email:    { color: "#ffd166", label: "email" },
    username: { color: "#b78cff", label: "username" },
    asn:      { color: "#7dffa8", label: "ASN" },
    place:    { color: "#ff9a5a", label: "luogo" },
  };

  let nodes = [], edges = [], adj = new Map(), selected = null;
  const el = () => document.getElementById("graphwin");
  const svg = () => document.getElementById("graph-svg");

  // --- Estrazione ------------------------------------------------------------
  const RE_EMAIL = /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g;
  const RE_IP = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
  const RE_ASN = /\bAS[\s]?(\d{2,6})\b/gi;
  const RE_DOMAIN = /\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b/gi;
  const BAD_TLD = /\.(html?|php|json|xml|css|js|png|jpe?g|gif|svg|txt|pdf|aspx?)$/i;

  function validIp(s) {
    return s.split(".").every(o => { const n = +o; return o.length && n >= 0 && n <= 255; });
  }
  function haversine(a, b) {
    const R = 6371, r = Math.PI / 180;
    const dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
    const s = Math.sin(dLat / 2) ** 2 +
      Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(s));
  }

  function nodeId(kind, val) { return kind + "|" + val; }

  function build() {
    const map = new Map();     // id -> node
    const emap = new Map();    // "a\tb" -> edge
    nodes = []; edges = [];
    function addNode(id, label, kind, extra) {
      let n = map.get(id);
      if (!n) { n = { id: id, label: label, kind: kind, deg: 0, extra: extra || {} }; map.set(id, n); nodes.push(n); }
      return n;
    }
    function addEdge(a, b, label, cls) {
      if (a === b) return;
      const k = a < b ? a + "\t" + b : b + "\t" + a;
      if (emap.has(k)) return;
      const e = { a: a, b: b, label: label || "", cls: cls || "shared" };
      emap.set(k, e); edges.push(e);
    }

    const items = (typeof dossier !== "undefined" && dossier) ? dossier : [];
    const geoEntries = [];
    items.forEach((it, i) => {
      const eid = "entry|" + i;
      const en = addNode(eid, it.title || (it.type + " #" + i), "entry",
        { type: it.type, via: it.via, time: it.time, target: it.target || "" });
      const text = [it.detail || "", it.target || "", (it.tags || []).join(" ")].join(" ");
      const seen = new Set();
      let budget = 22;
      const link = (kind, raw) => {
        const val = (raw || "").trim().toLowerCase();
        if (!val || seen.has(kind + val) || budget <= 0) return;
        seen.add(kind + val); budget--;
        const disp = kind === "asn" ? val.toUpperCase() : val;
        addNode(nodeId(kind, val), disp, kind);
        addEdge(eid, nodeId(kind, val), KIND[kind] ? KIND[kind].label : kind, "shared");
      };
      // target esplicito della voce
      if (it.target) {
        if (RE_EMAIL.test(it.target)) link("email", it.target);
        else if (RE_IP.test(it.target) && validIp(it.target)) link("ip", it.target);
        else if (it.type === "socmint") link("username", it.target);
        else if (/\./.test(it.target)) link("domain", it.target);
        RE_EMAIL.lastIndex = RE_IP.lastIndex = 0;
      }
      // estrazione dal testo
      (text.match(RE_EMAIL) || []).forEach(x => link("email", x));
      const emails = new Set((text.match(RE_EMAIL) || []).map(x => x.toLowerCase()));
      (text.match(RE_IP) || []).forEach(x => { if (validIp(x)) link("ip", x); });
      let m;
      RE_ASN.lastIndex = 0;
      while ((m = RE_ASN.exec(text))) link("asn", "AS" + m[1]);
      let dc = 0;
      (text.match(RE_DOMAIN) || []).forEach(x => {
        const d = x.toLowerCase();
        if (BAD_TLD.test(d)) return;
        if (/^\d+\.\d+\.\d+\.\d+$/.test(d)) return;
        // salta i domini che sono la parte destra di un'email già mappata
        let inEmail = false;
        emails.forEach(e => { if (e.endsWith("@" + d)) inEmail = true; });
        if (inEmail) return;
        if (dc++ >= 12) return;
        link("domain", d);
      });
      // luogo (coordinate)
      if (typeof it.lat === "number" && typeof it.lon === "number") {
        const key = it.lat.toFixed(3) + "," + it.lon.toFixed(3);
        addNode(nodeId("place", key), key, "place", { lat: it.lat, lon: it.lon });
        addEdge(eid, nodeId("place", key), "luogo", "shared");
        geoEntries.push({ id: eid, lat: it.lat, lon: it.lon });
      }
      en.extra.dt = it.iso || it.time || "";
    });

    // Archi di VICINANZA geografica fra voci (<= 60 km)
    for (let a = 0; a < geoEntries.length; a++)
      for (let b = a + 1; b < geoEntries.length; b++) {
        const d = haversine(geoEntries[a], geoEntries[b]);
        if (d <= 60) addEdge(geoEntries[a].id, geoEntries[b].id,
          "vicino " + d.toFixed(0) + " km", "geo");
      }

    // Archi TEMPORALI fra voci (<= 60 min)
    const timed = items.map((it, i) => ({ id: "entry|" + i, t: Date.parse(it.iso || "") }))
      .filter(x => !isNaN(x.t));
    for (let a = 0; a < timed.length; a++)
      for (let b = a + 1; b < timed.length; b++)
        if (Math.abs(timed[a].t - timed[b].t) <= 3600000)
          addEdge(timed[a].id, timed[b].id, "stessa finestra", "time");

    // gradi + adiacenze
    adj = new Map();
    nodes.forEach(n => adj.set(n.id, new Set()));
    edges.forEach(e => { e.a && adj.get(e.a).add(e.b); adj.get(e.b).add(e.a); e && (byDeg(e.a), byDeg(e.b)); });
    function byDeg(id) { const n = map.get(id); if (n) n.deg++; }

    layout();
    render();
    const cnt = document.getElementById("graph-count");
    if (cnt) cnt.textContent = nodes.length + " nodi · " + edges.length + " legami";
    const note = document.getElementById("graph-note");
    if (note) note.textContent = nodes.length
      ? "Trascina i nodi. Clic su un nodo per isolarne le connessioni."
      : "Dossier vuoto: aggiungi voci (GEOINT, recon, SOCMINT, correlazioni) e riapri.";
  }

  // --- Layout force-directed (Fruchterman-Reingold) --------------------------
  function layout() {
    const n = nodes.length;
    if (!n) return;
    const area = W * H, k = Math.sqrt(area / n) * 0.8;
    // init su cerchio
    nodes.forEach((nd, i) => {
      if (nd.fx == null) {
        const a = (i / n) * Math.PI * 2;
        nd.x = W / 2 + Math.cos(a) * W / 4 + (Math.random() - 0.5) * 20;
        nd.y = H / 2 + Math.sin(a) * H / 4 + (Math.random() - 0.5) * 20;
      }
    });
    const idx = new Map(nodes.map((nd, i) => [nd.id, i]));
    let temp = W / 8;
    const ITER = n > 120 ? 160 : 300;
    for (let it = 0; it < ITER; it++) {
      const dx = new Float64Array(n), dy = new Float64Array(n);
      // repulsione
      for (let i = 0; i < n; i++)
        for (let j = i + 1; j < n; j++) {
          let vx = nodes[i].x - nodes[j].x, vy = nodes[i].y - nodes[j].y;
          let d = Math.hypot(vx, vy) || 0.01;
          const f = (k * k) / d;
          vx = vx / d * f; vy = vy / d * f;
          dx[i] += vx; dy[i] += vy; dx[j] -= vx; dy[j] -= vy;
        }
      // attrazione lungo gli archi
      edges.forEach(e => {
        const i = idx.get(e.a), j = idx.get(e.b);
        if (i == null || j == null) return;
        let vx = nodes[i].x - nodes[j].x, vy = nodes[i].y - nodes[j].y;
        let d = Math.hypot(vx, vy) || 0.01;
        const f = (d * d) / k;
        vx = vx / d * f; vy = vy / d * f;
        dx[i] -= vx; dy[i] -= vy; dx[j] += vx; dy[j] += vy;
      });
      // spostamento limitato dalla temperatura + gravità
      for (let i = 0; i < n; i++) {
        if (nodes[i].fx != null) { nodes[i].x = nodes[i].fx; nodes[i].y = nodes[i].fy; continue; }
        let d = Math.hypot(dx[i], dy[i]) || 0.01;
        nodes[i].x += dx[i] / d * Math.min(d, temp);
        nodes[i].y += dy[i] / d * Math.min(d, temp);
        nodes[i].x += (W / 2 - nodes[i].x) * 0.01;
        nodes[i].y += (H / 2 - nodes[i].y) * 0.01;
      }
      temp *= 0.97;
    }
    // normalizza per riempire il viewBox con margine
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(nd => { minX = Math.min(minX, nd.x); minY = Math.min(minY, nd.y); maxX = Math.max(maxX, nd.x); maxY = Math.max(maxY, nd.y); });
    const pad = 46, sx = (W - 2 * pad) / (maxX - minX || 1), sy = (H - 2 * pad) / (maxY - minY || 1);
    const s = Math.min(sx, sy);
    nodes.forEach(nd => { nd.x = pad + (nd.x - minX) * s; nd.y = pad + (nd.y - minY) * s; });
  }

  // --- Render ----------------------------------------------------------------
  function radius(nd) { return nd.kind === "entry" ? 9 + Math.min(nd.deg, 8) : 5 + Math.min(nd.deg, 6); }

  function render() {
    const s = svg();
    if (!s) return;
    s.setAttribute("viewBox", "0 0 " + W + " " + H);
    while (s.firstChild) s.removeChild(s.firstChild);
    const gE = document.createElementNS(SVGNS, "g");
    const gN = document.createElementNS(SVGNS, "g");
    s.appendChild(gE); s.appendChild(gN);
    const pos = new Map(nodes.map(nd => [nd.id, nd]));

    edges.forEach(e => {
      const a = pos.get(e.a), b = pos.get(e.b);
      if (!a || !b) return;
      const ln = document.createElementNS(SVGNS, "line");
      ln.setAttribute("x1", a.x); ln.setAttribute("y1", a.y);
      ln.setAttribute("x2", b.x); ln.setAttribute("y2", b.y);
      ln.setAttribute("class", "gedge gedge-" + e.cls);
      ln.dataset.a = e.a; ln.dataset.b = e.b;
      const t = document.createElementNS(SVGNS, "title");
      t.textContent = e.label; ln.appendChild(t);
      gE.appendChild(ln);
    });

    nodes.forEach(nd => {
      const g = document.createElementNS(SVGNS, "g");
      g.setAttribute("class", "gnode gnode-" + nd.kind);
      g.setAttribute("transform", "translate(" + nd.x + "," + nd.y + ")");
      g.dataset.id = nd.id;
      const c = document.createElementNS(SVGNS, "circle");
      c.setAttribute("r", radius(nd));
      c.setAttribute("fill", (KIND[nd.kind] || KIND.entry).color);
      g.appendChild(c);
      const label = nd.kind === "entry" ? nd.label : nd.label;
      const tx = document.createElementNS(SVGNS, "text");
      tx.setAttribute("x", radius(nd) + 3); tx.setAttribute("y", 4);
      tx.textContent = label.length > 34 ? label.slice(0, 33) + "…" : label;
      g.appendChild(tx);
      const ti = document.createElementNS(SVGNS, "title");
      ti.textContent = (KIND[nd.kind] || {}).label + ": " + nd.label +
        (nd.extra && nd.extra.via ? "  ·  " + nd.extra.via : "");
      g.appendChild(ti);
      gN.appendChild(g);
      attachNodeEvents(g, nd);
    });
    exposeSVG();
  }

  // --- Interazione: drag + selezione ----------------------------------------
  function attachNodeEvents(g, nd) {
    let moved = false, drag = false, sx0, sy0, nx0, ny0;
    g.addEventListener("pointerdown", ev => {
      ev.stopPropagation();
      drag = true; moved = false;
      const p = svgPoint(ev); sx0 = p.x; sy0 = p.y; nx0 = nd.x; ny0 = nd.y;
      try { g.setPointerCapture(ev.pointerId); } catch (e) {}
    });
    g.addEventListener("pointermove", ev => {
      if (!drag) return;
      const p = svgPoint(ev);
      nd.x = nx0 + (p.x - sx0); nd.y = ny0 + (p.y - sy0);
      if (Math.abs(p.x - sx0) + Math.abs(p.y - sy0) > 3) moved = true;
      nd.fx = nd.x; nd.fy = nd.y;           // fissa il nodo dopo il trascinamento
      g.setAttribute("transform", "translate(" + nd.x + "," + nd.y + ")");
      updateEdges(nd.id);
    });
    g.addEventListener("pointerup", ev => {
      drag = false;
      try { g.releasePointerCapture(ev.pointerId); } catch (e) {}
      if (!moved) selectNode(nd.id === selected ? null : nd.id);
      exposeSVG();
    });
  }
  function svgPoint(ev) {
    const s = svg(), r = s.getBoundingClientRect();
    return { x: (ev.clientX - r.left) / r.width * W, y: (ev.clientY - r.top) / r.height * H };
  }
  function updateEdges(id) {
    const s = svg(); if (!s) return;
    const nd = nodes.find(n => n.id === id);
    s.querySelectorAll(".gedge").forEach(ln => {
      if (ln.dataset.a === id) { ln.setAttribute("x1", nd.x); ln.setAttribute("y1", nd.y); }
      if (ln.dataset.b === id) { ln.setAttribute("x2", nd.x); ln.setAttribute("y2", nd.y); }
    });
  }
  function selectNode(id) {
    selected = id;
    const s = svg(); if (!s) return;
    if (!id) {
      s.querySelectorAll(".gnode,.gedge").forEach(x => x.classList.remove("dim", "hot"));
      return;
    }
    const near = adj.get(id) || new Set();
    s.querySelectorAll(".gnode").forEach(g => {
      const on = g.dataset.id === id || near.has(g.dataset.id);
      g.classList.toggle("dim", !on); g.classList.toggle("hot", g.dataset.id === id);
    });
    s.querySelectorAll(".gedge").forEach(ln => {
      const on = ln.dataset.a === id || ln.dataset.b === id;
      ln.classList.toggle("dim", !on); ln.classList.toggle("hot", on);
    });
    exposeSVG();
  }

  // --- SVG per l'export e per il report --------------------------------------
  function styledSVG() {
    const s = svg(); if (!s) return "";
    const css =
      ".gedge{stroke:#2b4b60;stroke-width:1}" +
      ".gedge-geo{stroke:#ff9a5a;stroke-dasharray:4 3}" +
      ".gedge-time{stroke:#7dffa8;stroke-dasharray:2 4}" +
      ".gedge.hot{stroke:#00e5ff;stroke-width:2}.gedge.dim{opacity:.12}" +
      ".gnode text{font:11px sans-serif;fill:#c8f5ff}" +
      ".gnode circle{stroke:#050a14;stroke-width:1.5}" +
      ".gnode.dim{opacity:.18}.gnode.hot circle{stroke:#fff;stroke-width:2}";
    const clone = s.cloneNode(true);
    clone.setAttribute("xmlns", SVGNS);
    clone.setAttribute("width", W); clone.setAttribute("height", H);
    const st = document.createElementNS(SVGNS, "style");
    st.textContent = css;
    const bg = document.createElementNS(SVGNS, "rect");
    bg.setAttribute("width", W); bg.setAttribute("height", H); bg.setAttribute("fill", "#050a14");
    clone.insertBefore(st, clone.firstChild);
    clone.insertBefore(bg, clone.firstChild.nextSibling);
    return clone.outerHTML;
  }
  function exposeSVG() { try { window.HORUS_graphSVG = nodes.length ? styledSVG() : ""; } catch (e) {} }

  // --- Legenda ---------------------------------------------------------------
  function renderLegend() {
    const box = document.getElementById("graph-legend");
    if (!box) return;
    box.innerHTML = Object.keys(KIND).map(k =>
      '<span class="glg"><i style="background:' + KIND[k].color + '"></i>' + esc(KIND[k].label) + "</span>").join("") +
      '<span class="glg"><i class="ln geo"></i>vicinanza</span>' +
      '<span class="glg"><i class="ln time"></i>tempo</span>';
  }

  // --- Wiring ----------------------------------------------------------------
  function open() {
    const w = el(); if (!w) return;
    w.hidden = false;
    renderLegend();
    build();
  }
  function close() { const w = el(); if (w) w.hidden = true; }

  function exportSVG() {
    const data = styledSVG();
    if (!data) return;
    const blob = new Blob([data], { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "horus-grafo-" + Date.now() + ".svg";
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  document.addEventListener("DOMContentLoaded", function () { /* no-op */ });
  const bind = (id, ev, fn) => { const e = document.getElementById(id); if (e) e.addEventListener(ev, fn); };
  bind("corr-graph-btn", "click", open);
  bind("graph-close", "click", close);
  bind("graph-refresh", "click", build);
  bind("graph-export", "click", exportSVG);
  bind("graph-expand", "click", () => { const w = el(); if (w) w.classList.toggle("expanded"); render(); });
  if (typeof makeDraggable === "function") makeDraggable("graphwin", "graph-head");

  // esposto per eventuali altri moduli
  window.HORUS_openGraph = open;
})();
