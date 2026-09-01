// ===========================================================================
// HORUS - SOCMINT (username sulle piattaforme social)
// ---------------------------------------------------------------------------
// Enumerazione di uno username (stile sherlock/maigret) tramite il backend, che
// interroga le piattaforme dal TUO IP o da Tor. I profili trovati sono
// cliccabili e finiscono nel dossier. Trovare un profilo NON prova l'identita'.
// Dipende da: esc, addDossier (app.js).
// ===========================================================================
(function () {
  "use strict";
  const runBtn = document.getElementById("soc-run");
  const userIn = document.getElementById("soc-user");
  const note = document.getElementById("soc-note");
  const out = document.getElementById("soc-results");
  if (!runBtn || !userIn) return;

  let last = null;

  async function run() {
    const u = userIn.value.trim();
    if (!u) { note.textContent = "Inserisci uno username."; return; }
    note.textContent = "Cerco su tutte le piattaforme…";
    out.innerHTML = "";
    runBtn.disabled = true;
    try {
      const r = await fetch("api/socmint", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u }),
      });
      const d = await r.json();
      if (d.error) { note.textContent = d.error; return; }
      last = d;
      render(d);
    } catch (e) {
      note.textContent = "Errore: " + (e.message || e);
    } finally {
      runBtn.disabled = false;
    }
  }

  function render(d) {
    note.textContent = "«" + d.username + "»: " + d.found_count +
      " profili trovati su " + d.checked + " piattaforme.";
    const found = d.results.filter(r => r.found === true);
    const maybe = d.results.filter(r => r.found === null);
    let h = "";
    if (found.length) {
      h += '<div class="soc-grp"><div class="soc-h">Trovati (' + found.length + ")</div>";
      found.forEach(r => { h += row(r, "ok"); });
      h += "</div>";
    }
    if (maybe.length) {
      h += '<div class="soc-grp"><div class="soc-h soc-h-amb">Incerti (' + maybe.length +
        ") — blocco/redirect/limite</div>";
      maybe.forEach(r => { h += row(r, "amb"); });
      h += "</div>";
    }
    if (found.length)
      h += '<p class="hint">Alcune piattaforme confermano il profilo solo con lo ' +
        "stato HTTP: verifica cliccando (possibili falsi positivi dove il sito " +
        "risponde 200 anche per utenti inesistenti).</p>";
    if (!found.length && !maybe.length)
      h += '<p class="hint">Nessun profilo trovato con questo username.</p>';
    if (found.length)
      h += '<button id="soc-dossier" class="btn btn-alt">Aggiungi i profili al dossier</button>';
    out.innerHTML = h;
    const db = document.getElementById("soc-dossier");
    if (db) db.addEventListener("click", () => {
      const lines = found.map(r => r.site + ": " + r.url);
      addDossier("socmint", "Username " + d.username + " (" + found.length + " profili)",
        lines.join("\n"));
      note.textContent = "Profili aggiunti al dossier (tab Report).";
    });
  }

  function row(r, cls) {
    return '<a class="soc-item ' + cls + '" href="' + esc(r.url) +
      '" target="_blank" rel="noopener">' +
      '<span class="soc-badge"></span>' +
      '<span class="soc-site">' + esc(r.site) + "</span>" +
      '<span class="soc-url">' + esc(r.url.replace(/^https?:\/\//, "")) + "</span>" +
      (r.status ? '<span class="soc-code">' + r.status + "</span>" : "") + "</a>";
  }

  runBtn.addEventListener("click", run);
  userIn.addEventListener("keydown", e => { if (e.key === "Enter") run(); });

  // Avvia la ricerca username da un valore esterno (pivot dall'email).
  function runFor(username) {
    userIn.value = username;
    userIn.scrollIntoView({ behavior: "smooth", block: "start" });
    run();
  }

  // ------------------------------------------------------------------------
  // Email: violazioni note (XposedOrNot) + Gravatar
  // ------------------------------------------------------------------------
  const emRun = document.getElementById("soc-email-run");
  const emIn = document.getElementById("soc-email");
  const emNote = document.getElementById("soc-email-note");
  const emOut = document.getElementById("soc-email-results");

  async function runEmail() {
    const em = emIn.value.trim();
    if (!em) { emNote.textContent = "Inserisci un'email."; return; }
    emNote.textContent = "Controllo violazioni e Gravatar…";
    emOut.innerHTML = "";
    emRun.disabled = true;
    try {
      const r = await fetch("api/email", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: em }),
      });
      const d = await r.json();
      if (d.error) { emNote.textContent = d.error; return; }
      renderEmail(d);
    } catch (e) {
      emNote.textContent = "Errore: " + (e.message || e);
    } finally {
      emRun.disabled = false;
    }
  }

  // Candidati username derivati dalla parte locale dell'email + eventuale
  // username Gravatar: un pivot per passare dall'email alle piattaforme social.
  function usernameCandidates(d) {
    const set = [];
    const push = v => { v = (v || "").trim(); if (v && v.length >= 2 && set.indexOf(v) < 0) set.push(v); };
    const local = String(d.email || "").split("@")[0].toLowerCase()
      .replace(/\+.*/, "");                       // togli l'alias +tag
    push(local);
    push(local.replace(/[._-]/g, ""));
    push(local.replace(/[._-]/g, "_"));
    push(local.replace(/[._-]/g, "."));
    if (d.gravatar) {
      push(d.gravatar.username);
      if (d.gravatar.profile) push(d.gravatar.profile.split("/").filter(Boolean).pop());
      (d.gravatar.accounts || []).forEach(a => { push(a.username); push(a.shortname); });
    }
    return set;
  }

  function renderEmail(d) {
    const nb = d.breaches ? d.breaches.length : 0;
    emNote.textContent = "«" + d.email + "»: " + nb + " violazioni" +
      (d.gravatar ? " · profilo Gravatar trovato" : "") +
      (d.breach_error ? " · fonte violazioni non raggiungibile" : "") + ".";
    let h = "";
    const cands = usernameCandidates(d);
    if (cands.length) {
      h += '<div class="soc-pivot"><div class="soc-h">Pivot → username</div>' +
        '<p class="hint">Deriva possibili username dall\'email e cercali sulle ' +
        "piattaforme. Sono ipotesi: un match non prova l'identità.</p><div class=\"soc-chips\">";
      cands.forEach(c => { h += '<button class="soc-chip" data-user="' + esc(c) + '">' +
        esc(c) + "</button>"; });
      h += "</div></div>";
    }
    const det = {};
    (d.breach_details || []).forEach(x => { if (x.name) det[x.name.toLowerCase()] = x; });
    if (nb) {
      h += '<div class="soc-grp"><div class="soc-h">Violazioni (' + nb + ")</div>";
      d.breaches.forEach(name => {
        const x = det[String(name).toLowerCase()];
        const meta = x ? [x.date, x.records ? (fmtNum(x.records) + " record") : "", x.data]
          .filter(Boolean).join(" · ") : "";
        h += '<div class="soc-item ok"><span class="soc-badge"></span>' +
          '<span class="soc-site">' + esc(name) + "</span>" +
          (meta ? '<span class="soc-url">' + esc(meta) + "</span>" : "") + "</div>";
      });
      h += "</div>";
    } else if (!d.breach_error) {
      h += '<p class="hint">Nessuna violazione nota per questa email (XposedOrNot).</p>';
    }
    if (d.gravatar) {
      const g = d.gravatar;
      h += '<div class="soc-grp"><div class="soc-h">Gravatar</div>' +
        '<div class="grav-card">';
      if (g.thumb) h += '<img class="grav-thumb" src="' + esc(g.thumb) +
        '?s=80" alt="" onerror="this.style.display=\'none\'">';
      h += '<div class="grav-info"><b>' + esc(g.name || "(senza nome)") + "</b>" +
        (g.location ? '<span class="ci-meta">' + esc(g.location) + "</span>" : "") +
        (g.profile ? '<a href="' + esc(g.profile) + '" target="_blank" rel="noopener">Profilo Gravatar &#8599;</a>' : "") +
        "</div></div>";
      (g.accounts || []).forEach(a => {
        h += '<a class="soc-item ok" href="' + esc(a.url) + '" target="_blank" rel="noopener">' +
          '<span class="soc-badge"></span><span class="soc-site">' + esc(a.name || "account") +
          '</span><span class="soc-url">' + esc(a.url.replace(/^https?:\/\//, "")) + "</span></a>";
      });
      h += "</div>";
    }
    if (nb || d.gravatar)
      h += '<button id="soc-email-dossier" class="btn btn-alt">Aggiungi al dossier</button>';
    emOut.innerHTML = h;
    emOut.querySelectorAll(".soc-chip").forEach(ch => {
      ch.addEventListener("click", () => runFor(ch.dataset.user));
    });
    const db = document.getElementById("soc-email-dossier");
    if (db) db.addEventListener("click", () => {
      const lines = [];
      if (nb) lines.push("Violazioni: " + d.breaches.join(", "));
      if (d.gravatar) {
        lines.push("Gravatar: " + (d.gravatar.name || "") + " " + (d.gravatar.profile || ""));
        (d.gravatar.accounts || []).forEach(a => lines.push("  " + (a.name || "") + ": " + a.url));
      }
      addDossier("email", "Email " + d.email, lines.join("\n"));
      emNote.textContent = "Aggiunto al dossier (tab Report).";
    });
  }

  function fmtNum(n) { try { return Number(n).toLocaleString(); } catch (e) { return n; } }

  if (emRun) {
    emRun.addEventListener("click", runEmail);
    emIn.addEventListener("keydown", e => { if (e.key === "Enter") runEmail(); });
  }
})();
