// ===========================================================================
// HORUS - Intelligence fotografica (EXIF)
// ---------------------------------------------------------------------------
// Carichi una foto: HORUS ne estrae i metadati IN LOCALE (parser nativo lato
// server, arricchito da exiftool se presente). Se la foto contiene le
// coordinate GPS, compare subito un marcatore sulla mappa e parte
// l'auto-correlazione (cosa c'era intorno a quel punto/ora). Resa grafica
// immediata, nessuna chiave.
// Dipende da: esc (app.js), HORUS_addPhoto/HORUS_openCorrelate (correlate.js).
// ===========================================================================
(function () {
  "use strict";

  const fileInput = document.getElementById("corr-photo-file");
  const btn = document.getElementById("corr-photo");
  const btnUrl = document.getElementById("corr-photo-url");
  const body = document.getElementById("corr-body");
  if (!fileInput || !btn) return;

  btn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    const f = fileInput.files && fileInput.files[0];
    if (f) analyze(f);
    fileInput.value = "";   // permette di ricaricare lo stesso file
  });
  if (btnUrl) btnUrl.addEventListener("click", showUrlForm);
  function showUrlForm() {
    if (typeof HORUS_openCorrelate === "function") HORUS_openCorrelate();
    body.innerHTML =
      '<div class="exif-urlform">' +
      '<label class="exif-urllbl">Indirizzo dell\'immagine (anche da un social)</label>' +
      '<div class="exif-urlrow">' +
      '<input id="exif-url-input" type="text" placeholder="https://…/foto.jpg" autocomplete="off">' +
      '<button id="exif-url-go" class="corr-btn">Analizza</button>' +
      "</div>" +
      '<p class="exif-urlhint">Sui social: apri il post, tasto destro sulla foto → ' +
      '«Copia indirizzo immagine». Nota: le piattaforme rimuovono di solito ' +
      "il GPS in fase di upload.</p></div>";
    const inp = document.getElementById("exif-url-input");
    const go = document.getElementById("exif-url-go");
    const run = () => { const u = inp.value.trim(); if (u) analyzeUrl(u); };
    go.addEventListener("click", run);
    inp.addEventListener("keydown", e => { if (e.key === "Enter") run(); });
    inp.focus();
  }

  async function analyzeUrl(url) {
    if (typeof HORUS_openCorrelate === "function") HORUS_openCorrelate();
    body.innerHTML = '<p class="corr-empty">Scarico e analizzo l\'immagine&hellip;</p>';
    try {
      const r = await fetch("api/exif", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url }),
      });
      const d = await r.json();
      if (d.error) { body.innerHTML = '<p class="corr-empty">EXIF: ' + esc(d.error) + "</p>"; return; }
      render(d, d.url || url);
    } catch (e) {
      body.innerHTML = '<p class="corr-empty">Errore analisi EXIF: ' + esc(e.message || e) + "</p>";
    }
  }

  // "YYYY:MM:DD HH:MM:SS" (formato EXIF) -> millisecondi
  function exifTimeMs(s) {
    if (!s || typeof s !== "string") return null;
    const m = s.match(/(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
    if (!m) return null;
    const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
    return isNaN(d.getTime()) ? null : d.getTime();
  }

  function readAsDataURL(file) {
    return new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = () => rej(new Error("lettura file"));
      r.readAsDataURL(file);
    });
  }

  async function analyze(file) {
    if (typeof HORUS_openCorrelate === "function") HORUS_openCorrelate();
    body.innerHTML = '<p class="corr-empty">Estraggo i metadati di ' +
      esc(file.name) + "&hellip;</p>";
    let dataUrl;
    try { dataUrl = await readAsDataURL(file); }
    catch (e) { body.innerHTML = '<p class="corr-empty">Impossibile leggere il file.</p>'; return; }
    try {
      const r = await fetch("api/exif", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: file.name, data: dataUrl }),
      });
      const d = await r.json();
      if (d.error) { body.innerHTML = '<p class="corr-empty">EXIF: ' + esc(d.error) + "</p>"; return; }
      if (!d.name) d.name = file.name;
      render(d, dataUrl);
    } catch (e) {
      body.innerHTML = '<p class="corr-empty">Errore analisi EXIF: ' + esc(e.message || e) + "</p>";
    }
  }

  function render(d, thumb) {
    const tags = d.tags || {};
    const order = ["Make", "Model", "LensModel", "DateTimeOriginal", "CreateDate",
      "ModifyDate", "Software", "FNumber", "ExposureTime", "ISO", "FocalLength",
      "ImageWidth", "ImageHeight", "Orientation", "SerialNumber", "GPSAltitude"];
    const seen = {};
    let rows = "";
    order.forEach(k => { if (tags[k] != null && tags[k] !== "") {
      seen[k] = 1; rows += tagRow(k, tags[k]); } });
    Object.keys(tags).forEach(k => { if (!seen[k] && tags[k] != null && tags[k] !== "")
      rows += tagRow(k, tags[k]); });

    let h = '<div class="corr-summary"><b>' + esc(d.name || "Foto") + "</b><span>" +
      "EXIF via " + esc(d.source || "nativo") + " · " + fmtSize(d.size) + "</span></div>";
    if (thumb) h += '<img class="exif-thumb" src="' + esc(thumb) + '" alt="" ' +
      'onerror="this.style.display=\'none\'">';
    if (d.gps) {
      const t = exifTimeMs(tags.DateTimeOriginal || tags.CreateDate);
      h += '<div class="exif-gps"><b>&#128205; Posizione GPS</b>' +
        "<div>" + d.gps.lat.toFixed(6) + ", " + d.gps.lon.toFixed(6) +
        (d.gps.alt != null ? " · " + Math.round(d.gps.alt) + " m" : "") + "</div>" +
        '<div class="exif-gps-act">Marcata sulla mappa e correlata automaticamente.</div></div>';
    } else {
      h += '<p class="exif-nogps">Nessuna coordinata GPS in questa foto ' +
        "(molte piattaforme social rimuovono il GPS in upload).</p>";
    }
    h += rows ? '<div class="corr-grp"><div class="cg-head">Metadati</div>' +
      '<table class="exif-tbl">' + rows + "</table></div>"
      : '<p class="corr-empty">Nessun metadato EXIF leggibile (foto ripulita o formato non JPEG).</p>';
    body.innerHTML = h;

    // Resa grafica immediata: se c'e' il GPS, plotta e correla.
    if (d.gps && typeof HORUS_addPhoto === "function") {
      const t = exifTimeMs(tags.DateTimeOriginal || tags.CreateDate);
      HORUS_addPhoto(d.gps.lat, d.gps.lon, d.name || "Foto", t);
    }
  }

  function tagRow(k, v) {
    if (Array.isArray(v)) v = v.join(", ");
    return "<tr><td>" + esc(k) + "</td><td>" + esc(String(v)) + "</td></tr>";
  }
  function fmtSize(n) {
    if (!n) return "";
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }
})();
