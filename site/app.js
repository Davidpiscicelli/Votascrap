/* Plénière — veille parlementaire. Site statique : lit les fichiers JSON de data/ produits par collect/build.py. */
(function () {
  "use strict";

  const PARL = { wal: "Wallonie", bxl: "Bruxelles", fwb: "FWB" };
  const STATUTS = ["déposé", "en commission", "rapport de commission", "adopté", "rejeté", "retiré"];
  const ST_CLASS = { "déposé": "st-depose", "en commission": "st-commission", "rapport de commission": "st-rapport",
    "adopté": "st-adopte", "rejeté": "st-rejete", "retiré": "st-retire" };
  const NATURES = { ensemble: "Vote sur l'ensemble", motion: "Motion", "résolution": "Résolution", amendement: "Amendement", article: "Article", autre: "Autre" };
  // ordre gauche → droite de l'hémicycle wallon
  const SPECTRE = ["PTB", "PS", "Ecolo", "Les Engagés", "cdH", "MR", "DéFI", "Indépendant", "Indépendante"];
  const PARTY_COLORS = { "PTB": "#9e1b1b", "PS": "#e2001a", "Ecolo": "#3a9d3a", "Les Engagés": "#00a99d", "cdH": "#f28c00",
    "MR": "#0b4ea2", "DéFI": "#d4127e", "Indépendant": "#8a94a0", "Indépendante": "#8a94a0" };
  const PAGE = 60;
  const STORE_KEY = "pleniere.suivis";

  const D = { meta: null, dossiers: [], votes: [], deputes: [], syntheses: [], fwb: [], resumes: {}, prompts: null,
    questions: null, recentes: [] };
  const byId = { d: new Map(), v: new Map(), e: new Map() };
  const ui = { limit: {}, filters: {} };
  const view = document.getElementById("view");

  // ------------------------------------------------------------ utilitaires
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  const fdate = (iso) => {
    if (!iso) return "";
    const [y, m, d] = iso.slice(0, 10).split("-");
    return `${+d} ${MOIS[+m - 1]} ${y}`;
  };
  const nf = (n) => Number(n || 0).toLocaleString("fr-BE");
  const themeLabel = (id) => (D.meta.themes.find((t) => t.id === id) || { label: id }).label;
  const parlBadge = (p, extra) => `<span class="parl ${esc(p)}">${esc(PARL[p] || p)}${extra ? " · " + esc(extra) : ""}</span>`;
  const statutPill = (s) => `<span class="pill ${ST_CLASS[s] || "st-depose"}">${esc(s)}</span>`;
  const radarMark = (x) => (x && x.radar ? `<span class="radar" title="${esc(D.meta.radar.description || "")}">Radar PME</span>` : "");
  const chips = (themes) => (themes && themes.length ? `<div class="chips">${themes.map((t) => `<span class="chip">${esc(themeLabel(t))}</span>`).join("")}</div>` : "");
  const partyColor = (p) => PARTY_COLORS[p] || "#8a94a0";
  const ext = (url, label) => (url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>` : "");

  function storeGet() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY) || "[]"); } catch (e) { return []; }
  }
  function storeSet(list) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(list)); } catch (e) { /* stockage indisponible */ }
  }
  function isFollowed(id) { return storeGet().includes(id); }
  function followBtn(id) {
    const on = isFollowed(id);
    return `<button class="follow" type="button" data-follow="${esc(id)}" aria-pressed="${on}">${on ? "Suivi" : "Suivre"}</button>`;
  }

  async function getJSON(name, fallback) {
    try {
      const r = await fetch("data/" + name, { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) {
      return fallback;
    }
  }

  async function ensureQuestions() {
    if (!D.questions) {
      view.innerHTML = '<p class="loading">Chargement des questions…</p>';
      D.questions = await getJSON("questions.json", []);
      D.questions.forEach((q) => { q._s = fold([q.titre, q.auteur, q.destinataire, q.num].join(" ")); });
    }
    return D.questions;
  }

  // ------------------------------------------------------------ filtres
  function filterState(name, defaults) {
    if (!ui.filters[name]) ui.filters[name] = Object.assign({}, defaults);
    return ui.filters[name];
  }
  function select(id, label, value, options) {
    return `<div class="field"><label for="${id}">${label}</label><select id="${id}">${options
      .map(([v, l]) => `<option value="${esc(v)}"${v === value ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></div>`;
  }
  function searchField(id, value, placeholder) {
    return `<div class="field grow"><label for="${id}">Rechercher</label><input type="search" id="${id}" value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="off"></div>`;
  }
  function radarToggle(id, on) {
    return `<label class="toggle" for="${id}"><input type="checkbox" id="${id}"${on ? " checked" : ""}> Radar PME seulement</label>`;
  }
  const themeOptions = () => [["", "Tous les thèmes"]].concat(D.meta.themes.map((t) => [t.id, t.label]));
  const parlOptions = (list) => [["", "Toutes"]].concat(list.map((p) => [p, PARL[p]]));

  function bindFilters(name, fields, rerender) {
    const st = ui.filters[name];
    fields.forEach(([id, key, kind]) => {
      const el = document.getElementById(id);
      if (!el) return;
      const ev = kind === "text" ? "input" : "change";
      el.addEventListener(ev, () => {
        st[key] = kind === "check" ? el.checked : el.value;
        ui.limit[name] = PAGE;
        rerender();
      });
    });
  }
  function moreButton(name, shown, total) {
    if (shown >= total) return "";
    return `<div class="more"><button type="button" data-more="${name}">Afficher ${Math.min(PAGE, total - shown)} de plus (${nf(total - shown)} restants)</button></div>`;
  }

  // ------------------------------------------------------------ éléments de liste
  function dossierRow(d) {
    const r = D.resumes[d.id];
    return `<div class="row">
      <div class="row-meta">${parlBadge(d.parl, d.assemblee === "ARCCC" ? "COCOM" : "")}<span class="num">${fdate(d.date_maj)}</span></div>
      <div class="row-main">
        <a class="row-title" href="#d.${esc(d.id)}">${esc(d.titre)}</a>
        ${r ? `<p class="row-brief">${esc(r.en_bref)}</p>` : ""}
        <span class="row-sub">${esc(d.type)} <span class="ref">${esc(d.num || "")}</span>${d.commission ? " · " + esc(d.commission) : ""}</span>
        ${chips(d.themes)}
      </div>
      <div class="row-side">${statutPill(d.statut)}${radarMark(d)}</div>
    </div>`;
  }

  function questionRow(q) {
    const who = q.auteur_id ? `<a href="#e.${esc(q.auteur_id)}">${esc(q.auteur)}</a>` : esc(q.auteur || "");
    return `<div class="row">
      <div class="row-meta">${parlBadge(q.parl)}<span class="num">${fdate(q.date)}</span></div>
      <div class="row-main">
        <a class="row-title" href="${esc(q.url || "#")}" target="_blank" rel="noopener">${esc(q.titre)}</a>
        <span class="row-sub">${esc(q.type)}${q.num ? ` <span class="ref">n° ${esc(q.num)}</span>` : ""} · ${who}${q.parti ? " (" + esc(q.parti) + ")" : ""} → ${esc(q.destinataire || "")}</span>
        ${chips(q.themes)}
      </div>
      <div class="row-side">${radarMark(q)}</div>
    </div>`;
  }

  function vbar(v) {
    const t = Math.max(1, v.votants || v.pour + v.contre + v.abstention);
    return `<div class="vbar" role="img" aria-label="${v.pour} oui, ${v.contre} non, ${v.abstention} abstentions">
      <i class="o" style="width:${(100 * v.pour) / t}%"></i><i class="a" style="width:${(100 * v.abstention) / t}%"></i><i class="n" style="width:${(100 * v.contre) / t}%"></i></div>`;
  }
  function vcount(v) {
    return `<span class="vcount"><span class="o">${v.pour}</span> oui · <span class="n">${v.contre}</span> non · <span class="a">${v.abstention}</span> abst.</span>`;
  }
  function voteTitle(v) {
    const d = v.dossier && byId.d.get(v.dossier);
    if (d) return `${NATURES[v.nature] || "Vote"} — ${d.titre}`;
    let o = (v.objet || "").replace(/^Nous (allons|passons)( à présent)? (voter|au vote) sur /i, "");
    o = o.charAt(0).toUpperCase() + o.slice(1);
    return o.length > 220 ? o.slice(0, 217) + "…" : o;
  }
  function voteRow(v) {
    return `<div class="row">
      <div class="row-meta">${parlBadge(v.parl)}<span class="num">${fdate(v.date)}</span><span class="ref">${esc(v.seance || "")}</span></div>
      <div class="row-main">
        <a class="row-title" href="#v.${esc(v.id)}">${esc(voteTitle(v))}</a>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">${vbar(v)}${vcount(v)}</div>
        ${v.dissidents && v.dissidents.length ? `<span class="row-sub">${v.dissidents.length} vote${v.dissidents.length > 1 ? "s" : ""} contre la ligne du groupe</span>` : ""}
      </div>
      <div class="row-side">${statutPill(v.resultat)}${radarMark(v)}</div>
    </div>`;
  }

  // ------------------------------------------------------------ accueil
  function lastSynthese() { return D.syntheses[0]; }

  function syntheseFeature(s, full) {
    if (!s) return "";
    const q = s.questions || {};
    const fallback = `${nf((q.wal || 0) + (q.bxl || 0))} questions aux ministres (${nf(q.wal || 0)} en Wallonie, ${nf(q.bxl || 0)} à Bruxelles), ${s.dossiers_deposes.length} dossiers déposés, ${s.dossiers_adoptes.length} textes adoptés et ${s.votes} votes nominatifs en plénière wallonne.`;
    const adoptes = s.dossiers_adoptes.map((id) => byId.d.get(id)).filter(Boolean);
    return `<section class="feature" aria-labelledby="syn-${s.mois}">
      <div class="block-head"><h2 id="syn-${s.mois}">${full ? "" : "Synthèse · "}${esc(s.libelle)}</h2>${full ? "" : '<a href="#syntheses">Toutes les synthèses</a>'}</div>
      <div class="figures">
        <div class="figure"><b>${nf((q.wal || 0) + (q.bxl || 0))}</b><span>questions</span></div>
        <div class="figure"><b>${s.dossiers_deposes.length}</b><span>dossiers déposés</span></div>
        <div class="figure"><b>${s.dossiers_adoptes.length}</b><span>textes adoptés</span></div>
        <div class="figure"><b>${s.votes}</b><span>votes nominatifs</span></div>
        <div class="figure"><b>${s.questions_radar}</b><span>questions radar PME</span></div>
      </div>
      <p class="texte">${esc(s.texte_ia || fallback)}</p>
      ${s.texte_ia ? '<p class="label">Texte rédigé par IA à partir des chiffres ci-dessus · <a href="#methode">méthode</a></p>' : ""}
      ${full && adoptes.length ? `<div class="mini">${adoptes.map((d) => `<div class="mini-item"><div class="mini-top">${parlBadge(d.parl)}${radarMark(d)}</div><a href="#d.${esc(d.id)}">${esc(d.titre)}</a></div>`).join("")}</div>` : ""}
    </section>`;
  }

  function themeBars(s) {
    if (!s || !s.themes.length) return "";
    const max = s.themes[0][1];
    return `<section class="block"><div class="block-head"><h3>Thèmes des questions · ${esc(s.libelle)}</h3></div>
      <div class="bars">${s.themes.map(([l, n]) => `<div class="bar"><span class="bar-l" title="${esc(l)}">${esc(l)}</span>
        <span class="bar-track"><span class="bar-fill" style="display:block;width:${(100 * n) / max}%"></span></span><span class="bar-n">${nf(n)}</span></div>`).join("")}</div>
      <p class="label">Une question peut relever de plusieurs thèmes.</p></section>`;
  }

  function radarFeed(n) {
    const items = [];
    D.dossiers.filter((d) => d.radar).forEach((d) => items.push({ date: d.date_maj, html: `<div class="mini-item"><div class="mini-top">${parlBadge(d.parl)}<span>${fdate(d.date_maj)}</span>${statutPill(d.statut)}</div><a href="#d.${esc(d.id)}">${esc(d.titre)}</a></div>` }));
    D.recentes.filter((q) => q.radar).forEach((q) => items.push({ date: q.date, html: `<div class="mini-item"><div class="mini-top">${parlBadge(q.parl)}<span>${fdate(q.date)}</span><span>${esc(q.type)} · ${esc(q.auteur)}</span></div><a href="${esc(q.url)}" target="_blank" rel="noopener">${esc(q.titre)}</a></div>` }));
    items.sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    return items.slice(0, n).map((i) => i.html).join("");
  }

  function renderHome() {
    const s = lastSynthese();
    const adoptes = D.dossiers.filter((d) => d.statut === "adopté").sort((a, b) => (b.date_maj || "").localeCompare(a.date_maj || "")).slice(0, 6);
    const finals = D.votes.filter((v) => ["ensemble", "motion", "résolution"].includes(v.nature)).slice(0, 6);
    view.innerHTML = `
      <div class="page-head"><h1>${esc(D.meta.site.accroche)}</h1>
        <p class="lede">${esc(D.meta.site.sous_titre)}. Dossiers, questions aux ministres et votes nominatifs, classés par thème, avec un radar pour ce qui touche les PME et les indépendants.</p></div>
      <div class="home">
        <div class="col">
          ${syntheseFeature(s)}
          <section class="block"><div class="block-head"><h2>Radar PME &amp; indépendants</h2><a href="#dossiers" data-radar="1">Tous les dossiers radar</a></div>
            <p class="muted">${esc(D.meta.radar.description || "")}</p>
            <div class="mini">${radarFeed(10) || '<p class="empty">Rien de neuf pour l’instant.</p>'}</div></section>
          <section class="block"><div class="block-head"><h2>Textes adoptés récemment</h2><a href="#dossiers">Tous les dossiers</a></div>
            <div class="rows">${adoptes.map(dossierRow).join("") || '<p class="empty">Aucun texte adopté.</p>'}</div></section>
        </div>
        <div class="col">
          <section class="block"><div class="block-head"><h3>Derniers votes en plénière</h3><a href="#votes">Tous les votes</a></div>
            <div class="mini">${finals.map((v) => `<div class="mini-item"><div class="mini-top">${parlBadge(v.parl)}<span>${fdate(v.date)}</span>${statutPill(v.resultat)}</div>
              <a href="#v.${esc(v.id)}">${esc(voteTitle(v))}</a><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">${vbar(v)}${vcount(v)}</div></div>`).join("") || '<p class="empty">Aucun vote chargé.</p>'}</div></section>
          ${themeBars(s)}
          <section class="block"><div class="block-head"><h3>Fédération Wallonie-Bruxelles</h3><a href="#fwb">Tous les documents</a></div>
            <div class="mini">${D.fwb.slice(0, 6).map((f) => `<div class="mini-item"><div class="mini-top">${parlBadge("fwb")}<span>${fdate(f.date)}</span><span>${esc(f.type)}</span></div>${ext(f.url, f.titre)}</div>`).join("") || '<p class="empty">Pas encore de document collecté.</p>'}</div></section>
        </div>
      </div>`;
    view.querySelectorAll("[data-radar]").forEach((a) => a.addEventListener("click", () => { filterState("dossiers", dossierDefaults).radar = true; }));
  }

  // ------------------------------------------------------------ dossiers
  const dossierDefaults = { parl: "", statut: "", theme: "", radar: false, q: "", tri: "maj" };
  function renderDossiers() {
    const st = filterState("dossiers", dossierDefaults);
    const lim = ui.limit.dossiers || PAGE;
    const qq = fold(st.q);
    let list = D.dossiers.filter((d) => (!st.parl || d.parl === st.parl) && (!st.statut || d.statut === st.statut)
      && (!st.theme || (d.themes || []).includes(st.theme)) && (!st.radar || d.radar) && (!qq || d._s.includes(qq)));
    list = list.slice().sort(st.tri === "depot" ? (a, b) => (b.date_depot || "").localeCompare(a.date_depot || "") : (a, b) => (b.date_maj || "").localeCompare(a.date_maj || ""));
    view.innerHTML = `
      <div class="page-head"><h1>Dossiers législatifs</h1><p class="lede">Projets et propositions de décret et d'ordonnance, résolutions et budgets, avec leur avancement.</p></div>
      <div class="filters">
        ${searchField("f-q", st.q, "Mot du titre, numéro, auteur…")}
        ${select("f-parl", "Parlement", st.parl, parlOptions(["wal", "bxl"]))}
        ${select("f-statut", "Statut", st.statut, [["", "Tous"]].concat(STATUTS.map((s) => [s, s])))}
        ${select("f-theme", "Thème", st.theme, themeOptions())}
        ${select("f-tri", "Trier par", st.tri, [["maj", "Dernière activité"], ["depot", "Date de dépôt"]])}
        ${radarToggle("f-radar", st.radar)}
      </div>
      <p class="count">${nf(list.length)} dossier${list.length > 1 ? "s" : ""}</p>
      <div class="rows">${list.slice(0, lim).map(dossierRow).join("") || '<p class="empty">Aucun dossier ne correspond à ces filtres.</p>'}</div>
      ${moreButton("dossiers", Math.min(lim, list.length), list.length)}`;
    bindFilters("dossiers", [["f-q", "q", "text"], ["f-parl", "parl"], ["f-statut", "statut"], ["f-theme", "theme"], ["f-tri", "tri"], ["f-radar", "radar", "check"]], renderDossiers);
    keepFocus();
  }

  function isKeyStep(e) {
    const l = fold(e.libelle);
    return e.t === "49" || e.t === "92" || /texte adopte|adopte\(e\) en seance|publie au moniteur|sanction/.test(l);
  }

  function renderDossier(id) {
    const d = byId.d.get(id);
    if (!d) return notFound();
    const r = D.resumes[d.id];
    const votes = (d.votes || []).map((x) => byId.v.get(x)).filter(Boolean);
    view.innerHTML = `
      <p class="crumbs"><a href="#dossiers">Dossiers</a></p>
      <div class="detail-head">
        <div class="meta-line">${parlBadge(d.parl, d.assemblee === "ARCCC" ? "COCOM" : "")}<span>${esc(d.type)}</span><span class="ref">${esc(d.num || "")}</span>${statutPill(d.statut)}${radarMark(d)}</div>
        <h1>${esc(d.titre)}</h1>
        <div class="meta-line"><span>Déposé le ${fdate(d.date_depot)}</span>${d.auteurs ? `<span>Auteurs : ${esc(d.auteurs)}</span>` : ""}${d.commission ? `<span>${esc(d.commission)}</span>` : ""}</div>
        <div class="links">${ext(d.url, "Fiche officielle")}${ext(d.pdf, "Document déposé (PDF)")}${followBtn(d.id)}</div>
        ${chips(d.themes)}
      </div>
      <div class="detail">
        <div class="col">
          ${r ? `<section class="ia" aria-label="Résumé en langage clair">
            <h3>En bref</h3><p class="bref">${esc(r.en_bref)}</p>
            <h3>Résumé</h3><p>${esc(r.resume)}</p>
            <div class="enjeux"><h3>Pour les entreprises</h3><p>${esc(r.enjeux_entreprises)}</p></div>
            ${r.points_attention && r.points_attention.length ? `<h3>Points d'attention</h3><ul>${r.points_attention.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : ""}
            ${r.public_concerne && r.public_concerne.length ? `<div class="chips">${r.public_concerne.map((p) => `<span class="chip">${esc(p)}</span>`).join("")}</div>` : ""}
            <p class="note">Résumé rédigé par IA (${esc(r.modele || "")}, ${fdate(r.genere_le)}) à partir de l'intitulé, des étapes et du début du document déposé. Le texte officiel fait foi · <a href="#methode">méthode</a></p>
          </section>` : `<section class="ia"><h3>Résumé</h3><p class="muted">Pas encore de résumé en langage clair pour ce dossier. Consultez la fiche officielle et le document déposé.</p></section>`}
          ${votes.length ? `<section class="block"><h2>Votes nominatifs</h2><div class="rows">${votes.map(voteRow).join("")}</div></section>` : ""}
        </div>
        <section class="block" aria-label="Chronologie"><h2>Chronologie</h2>
          ${d.etapes && d.etapes.length ? `<ol class="timeline">${d.etapes.slice().sort((a, b) => (a.date || "").localeCompare(b.date || "")).map((e) => `<li class="${isKeyStep(e) ? "key" : ""}">
            <span class="when">${fdate(e.date)}</span><span class="what">${esc(e.libelle)}${e.auteurs && e.auteurs !== "p.m." ? ` <span class="muted">· ${esc(e.auteurs)}</span>` : ""}</span>
            ${e.url ? `<span class="ref">${ext(e.url, e.doc || "document")}</span>` : ""}</li>`).join("")}</ol>` : '<p class="muted">Chronologie non disponible.</p>'}
        </section>
      </div>`;
  }

  // ------------------------------------------------------------ questions
  const questionDefaults = { parl: "", type: "", theme: "", radar: false, q: "", ministre: "" };
  async function renderQuestions() {
    const all = await ensureQuestions();
    const st = filterState("questions", questionDefaults);
    const lim = ui.limit.questions || PAGE;
    const qq = fold(st.q);
    const types = [...new Set(all.map((q) => q.type))].sort();
    const ministres = [...new Set(all.filter((q) => !st.parl || q.parl === st.parl).map((q) => q.destinataire).filter(Boolean))].sort();
    const list = all.filter((q) => (!st.parl || q.parl === st.parl) && (!st.type || q.type === st.type)
      && (!st.theme || (q.themes || []).includes(st.theme)) && (!st.radar || q.radar)
      && (!st.ministre || q.destinataire === st.ministre) && (!qq || q._s.includes(qq)));
    view.innerHTML = `
      <div class="page-head"><h1>Questions aux ministres</h1><p class="lede">Questions écrites, orales, d'actualité et interpellations de la législature en cours.</p></div>
      <div class="filters">
        ${searchField("q-q", st.q, "Mot du titre, député, numéro…")}
        ${select("q-parl", "Parlement", st.parl, parlOptions(["wal", "bxl"]))}
        ${select("q-type", "Type", st.type, [["", "Tous"]].concat(types.map((t) => [t, t])))}
        ${select("q-theme", "Thème", st.theme, themeOptions())}
        ${select("q-min", "Ministre", st.ministre, [["", "Tous"]].concat(ministres.map((m) => [m, m])))}
        ${radarToggle("q-radar", st.radar)}
      </div>
      <p class="count">${nf(list.length)} question${list.length > 1 ? "s" : ""}</p>
      <div class="rows">${list.slice(0, lim).map(questionRow).join("") || '<p class="empty">Aucune question ne correspond à ces filtres.</p>'}</div>
      ${moreButton("questions", Math.min(lim, list.length), list.length)}`;
    bindFilters("questions", [["q-q", "q", "text"], ["q-parl", "parl"], ["q-type", "type"], ["q-theme", "theme"], ["q-min", "ministre"], ["q-radar", "radar", "check"]], renderQuestions);
    keepFocus();
  }

  // ------------------------------------------------------------ votes
  const voteDefaults = { nature: "", resultat: "", theme: "", radar: false, divise: false, q: "" };
  function renderVotes() {
    const st = filterState("votes", voteDefaults);
    const lim = ui.limit.votes || PAGE;
    const qq = fold(st.q);
    const list = D.votes.filter((v) => (!st.nature || v.nature === st.nature) && (!st.resultat || v.resultat === st.resultat)
      && (!st.theme || (v.themes || []).includes(st.theme)) && (!st.radar || v.radar) && (!st.divise || v.contre > 0)
      && (!qq || v._s.includes(qq)));
    view.innerHTML = `
      <div class="page-head"><h1>Votes nominatifs</h1><p class="lede">Séances plénières du Parlement de Wallonie : qui a voté oui, non ou s'est abstenu, et les votes contre la ligne de son groupe.</p></div>
      <div class="filters">
        ${searchField("v-q", st.q, "Objet du vote, numéro de document…")}
        ${select("v-nature", "Nature", st.nature, [["", "Toutes"]].concat(Object.entries(NATURES)))}
        ${select("v-res", "Résultat", st.resultat, [["", "Tous"], ["adopté", "Adopté"], ["rejeté", "Rejeté"]])}
        ${select("v-theme", "Thème", st.theme, themeOptions())}
        <label class="toggle" for="v-div"><input type="checkbox" id="v-div"${st.divise ? " checked" : ""}> Votes divisés seulement</label>
        ${radarToggle("v-radar", st.radar)}
      </div>
      <p class="count">${nf(list.length)} vote${list.length > 1 ? "s" : ""}</p>
      <div class="rows">${list.slice(0, lim).map(voteRow).join("") || '<p class="empty">Aucun vote ne correspond à ces filtres.</p>'}</div>
      ${moreButton("votes", Math.min(lim, list.length), list.length)}`;
    bindFilters("votes", [["v-q", "q", "text"], ["v-nature", "nature"], ["v-res", "resultat"], ["v-theme", "theme"], ["v-div", "divise", "check"], ["v-radar", "radar", "check"]], renderVotes);
    keepFocus();
  }

  function hemicycle(v) {
    // sièges : membres connus de chaque groupe (y compris absents), groupés de gauche à droite
    const pos = new Map(v.positions.map(([who, p, parti]) => [who, { p, parti }]));
    const seats = [];
    const deps = D.deputes.filter((d) => d.parl === v.parl);
    const parties = [...new Set(deps.map((d) => d.parti).concat(v.positions.map((x) => x[2])))];
    parties.sort((a, b) => (SPECTRE.indexOf(a) + 1 || 99) - (SPECTRE.indexOf(b) + 1 || 99));
    const rank = { o: 0, a: 1, n: 2, x: 3 };
    parties.forEach((party) => {
      const group = [];
      deps.filter((d) => d.parti === party).forEach((d) => group.push({ party, p: pos.has(d.id) ? pos.get(d.id).p : "x", name: d.nom_complet }));
      v.positions.filter(([who, , pa]) => pa === party && !byId.e.has(who)).forEach(([who, p]) => group.push({ party, p, name: who }));
      group.sort((a, b) => rank[a.p] - rank[b.p]);
      seats.push(...group);
    });
    const n = seats.length;
    if (!n) return "";
    const rows = Math.max(3, Math.round(Math.sqrt(n / 3)));
    const r0 = 38, r1 = 92, radii = Array.from({ length: rows }, (_, i) => r0 + ((r1 - r0) * i) / (rows - 1));
    const sum = radii.reduce((a, b) => a + b, 0);
    let counts = radii.map((r) => Math.round((n * r) / sum));
    counts[rows - 1] += n - counts.reduce((a, b) => a + b, 0);
    const pts = [];
    radii.forEach((r, i) => {
      const k = counts[i];
      for (let j = 0; j < k; j++) {
        const a = Math.PI - (k === 1 ? Math.PI / 2 : (Math.PI * j) / (k - 1));
        pts.push({ a, x: 100 + r * Math.cos(a), y: 98 - r * Math.sin(a) });
      }
    });
    pts.sort((p, q) => q.a - p.a || 0);
    const dot = Math.min(4.2, 150 / n + 1.6);
    const fill = { o: "var(--oui)", n: "var(--non)", a: "var(--abst)", x: "var(--absent)" };
    const label = { o: "oui", n: "non", a: "abstention", x: "absent" };
    const circles = seats.map((s, i) => `<circle cx="${pts[i].x.toFixed(1)}" cy="${pts[i].y.toFixed(1)}" r="${dot}" fill="${fill[s.p]}" stroke="${partyColor(s.party)}" stroke-width="1.1"><title>${esc(s.name)} (${esc(s.party)}) : ${label[s.p]}</title></circle>`).join("");
    return `<div class="hemi-wrap"><svg class="hemi" viewBox="0 0 200 104" role="img" aria-label="Hémicycle : ${v.pour} oui, ${v.contre} non, ${v.abstention} abstentions">${circles}
      <text x="100" y="96" text-anchor="middle" font-size="9" font-weight="700" fill="var(--ink)" font-family="var(--font-body)">${v.pour} – ${v.contre}</text></svg>
      <div class="legend"><span><i style="background:var(--oui)"></i>Oui</span><span><i style="background:var(--non)"></i>Non</span><span><i style="background:var(--abst)"></i>Abstention</span><span><i style="background:var(--absent)"></i>Absent ou non relevé</span><span class="muted">Contour : couleur du groupe</span></div></div>`;
  }

  function renderVote(id) {
    const v = byId.v.get(id);
    if (!v) return notFound();
    const d = v.dossier && byId.d.get(v.dossier);
    const parties = Object.keys(v.partis || {}).sort((a, b) => (SPECTRE.indexOf(a) + 1 || 99) - (SPECTRE.indexOf(b) + 1 || 99));
    const dissidents = (v.dissidents || []).map((w) => {
      const p = v.positions.find((x) => x[0] === w);
      const e = byId.e.get(w);
      const pos = { o: "oui", n: "non", a: "abstention" }[p ? p[1] : ""] || "";
      return `<li>${e ? `<a href="#e.${esc(w)}">${esc(e.nom_complet)}</a>` : esc(w)} (${esc(p ? p[2] : "")}) : ${pos}, contre la ligne du groupe (${esc(({ oui: "oui", non: "non", abst: "abstention" })[v.ligne[p ? p[2] : ""]] || "")})</li>`;
    });
    const hasNames = v.positions && v.positions.length;
    view.innerHTML = `
      <p class="crumbs"><a href="#votes">Votes</a></p>
      <div class="detail-head">
        <div class="meta-line">${parlBadge(v.parl)}<span>${fdate(v.date)}</span><span class="ref">${esc(v.seance)}</span><span>${esc(NATURES[v.nature] || "")}</span>${statutPill(v.resultat)}${radarMark(v)}</div>
        <h1>${esc(voteTitle(v))}</h1>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">${vbar(v)}${vcount(v)}<span class="muted">${v.votants} votants</span></div>
        ${v.resultat_deduit ? '<p class="label">Résultat déduit des décomptes (oui &gt; non) ; vérifier dans le compte rendu pour les majorités spéciales.</p>' : ""}
        <div class="links">${ext(v.url, "Compte rendu intégral (PDF)")}${d ? `<a href="#d.${esc(d.id)}">Dossier : ${esc(d.num)}</a>` : ""}</div>
      </div>
      <div class="detail">
        <div class="col">
          ${hasNames ? hemicycle(v) : '<p class="muted">Le détail nominatif de ce vote n’a pas pu être relevé automatiquement ; les décomptes ci-dessus sont ceux du compte rendu.</p>'}
          <section class="block"><h2>Objet du vote</h2><p>${esc(v.objet)}</p></section>
        </div>
        <div class="col">
          ${parties.length ? `<section class="block"><h2>Par groupe</h2><div class="table-wrap"><table><thead><tr><th>Groupe</th><th class="n">Oui</th><th class="n">Non</th><th class="n">Abst.</th></tr></thead><tbody>
            ${parties.map((p) => `<tr><td><span class="dot" style="background:${partyColor(p)}"></span>${esc(p)}</td><td class="n">${v.partis[p].oui}</td><td class="n">${v.partis[p].non}</td><td class="n">${v.partis[p].abst}</td></tr>`).join("")}</tbody></table></div></section>` : ""}
          ${dissidents.length ? `<section class="block"><h2>Votes contre la ligne du groupe</h2><ul>${dissidents.join("")}</ul></section>` : ""}
        </div>
      </div>`;
  }

  // ------------------------------------------------------------ élus
  const eluDefaults = { parti: "", tri: "questions", q: "" };
  function renderElus() {
    const st = filterState("elus", eluDefaults);
    const qq = fold(st.q);
    const parties = [...new Set(D.deputes.map((d) => d.parti))].sort((a, b) => (SPECTRE.indexOf(a) + 1 || 99) - (SPECTRE.indexOf(b) + 1 || 99));
    const finals = D.votes.filter((v) => v.positions && v.positions.length);
    const summary = parties.map((p) => {
      const members = D.deputes.filter((d) => d.parti === p);
      const ids = new Set(members.map((m) => m.id));
      const concerned = finals.filter((v) => v.partis && v.partis[p] && (v.partis[p].oui + v.partis[p].non + v.partis[p].abst) >= 2);
      const united = concerned.filter((v) => !(v.dissidents || []).some((w) => ids.has(w))).length;
      return { p, n: members.length, q: members.reduce((a, m) => a + m.questions, 0), coh: concerned.length ? Math.round((100 * united) / concerned.length) : null };
    });
    let list = D.deputes.filter((d) => (!st.parti || d.parti === st.parti) && (!qq || fold(d.nom_complet + " " + d.circonscription).includes(qq)));
    list = list.slice().sort(st.tri === "nom" ? (a, b) => a.nom.localeCompare(b.nom) : st.tri === "dissidences" ? (a, b) => b.dissidences - a.dissidences : (a, b) => b.questions - a.questions);
    view.innerHTML = `
      <div class="page-head"><h1>Élus · Parlement de Wallonie</h1><p class="lede">Activité de contrôle et votes des ${D.deputes.length} députés de la législature en cours.</p></div>
      <section class="block"><h2>Groupes politiques</h2><div class="table-wrap"><table>
        <thead><tr><th>Groupe</th><th class="n">Sièges</th><th class="n">Questions</th><th class="n">Votes unanimes dans le groupe</th></tr></thead><tbody>
        ${summary.map((s) => `<tr><td><span class="dot" style="background:${partyColor(s.p)}"></span>${esc(s.p)}</td><td class="n">${s.n}</td><td class="n">${nf(s.q)}</td><td class="n">${s.coh == null ? "–" : s.coh + " %"}</td></tr>`).join("")}
        </tbody></table></div><p class="label">« Votes unanimes dans le groupe » : part des votes nominatifs où aucun membre du groupe ne s'est écarté de la position majoritaire du groupe.</p></section>
      <div class="filters">
        ${searchField("e-q", st.q, "Nom, circonscription…")}
        ${select("e-parti", "Groupe", st.parti, [["", "Tous"]].concat(parties.map((p) => [p, p])))}
        ${select("e-tri", "Trier par", st.tri, [["questions", "Nombre de questions"], ["dissidences", "Votes contre la ligne"], ["nom", "Nom"]])}
      </div>
      <div class="cards">${list.map((d) => `<a class="card" href="#e.${esc(d.id)}">
        ${d.photo ? `<img src="${esc(d.photo)}" alt="" loading="lazy">` : '<span class="avatar"></span>'}
        <span style="display:flex;flex-direction:column;gap:3px;min-width:0"><span class="who">${esc(d.nom_complet)}</span>
        <span class="party-line"><span class="dot" style="background:${partyColor(d.parti)}"></span>${esc(d.parti)} · ${esc(d.circonscription)}</span>
        <span class="stats">${nf(d.questions)} questions · ${nf(d.votes)} votes · ${nf(d.dissidences)} contre la ligne</span></span></a>`).join("")}</div>`;
    bindFilters("elus", [["e-q", "q", "text"], ["e-parti", "parti"], ["e-tri", "tri"]], renderElus);
    keepFocus();
  }

  async function renderElu(id) {
    const e = byId.e.get(id);
    if (!e) return notFound();
    const qs = (await ensureQuestions()).filter((q) => q.auteur_id === id);
    const diss = D.votes.filter((v) => (v.dissidents || []).includes(id));
    const lim = ui.limit["elu-" + id] || 20;
    view.innerHTML = `
      <p class="crumbs"><a href="#elus">Élus</a></p>
      <div class="detail-head" style="flex-direction:row;gap:18px;align-items:flex-start;flex-wrap:wrap">
        ${e.photo ? `<img src="${esc(e.photo)}" alt="" style="width:96px;height:120px;object-fit:cover;border-radius:6px">` : ""}
        <div style="display:flex;flex-direction:column;gap:8px;min-width:0">
          <h1>${esc(e.nom_complet)}</h1>
          <span class="party-line"><span class="dot" style="background:${partyColor(e.parti)}"></span>${esc(e.parti)} · ${esc(e.circonscription)}</span>
          <div class="figures"><div class="figure"><b>${nf(e.questions)}</b><span>questions</span></div><div class="figure"><b>${nf(e.votes)}</b><span>votes relevés</span></div><div class="figure"><b>${nf(e.dissidences)}</b><span>contre la ligne</span></div></div>
          ${chips(e.themes)}
          <div class="links">${ext(e.url, "Page officielle")}${followBtn(e.id)}</div>
        </div>
      </div>
      <div class="detail">
        <section class="block"><h2>Questions récentes</h2><div class="rows">${qs.slice(0, lim).map(questionRow).join("") || '<p class="empty">Aucune question.</p>'}</div>${moreButton("elu-" + id, Math.min(lim, qs.length), qs.length)}</section>
        <section class="block"><h2>Votes contre la ligne du groupe</h2>${diss.length ? `<div class="mini">${diss.map((v) => `<div class="mini-item"><div class="mini-top"><span>${fdate(v.date)}</span>${statutPill(v.resultat)}</div><a href="#v.${esc(v.id)}">${esc(voteTitle(v))}</a></div>`).join("")}</div>` : '<p class="muted">Aucun vote contre la ligne de son groupe relevé.</p>'}</section>
      </div>`;
  }

  // ------------------------------------------------------------ synthèses, FWB, suivis, méthode
  function renderSyntheses() {
    view.innerHTML = `<div class="page-head"><h1>Synthèses mensuelles</h1><p class="lede">Chaque mois en chiffres : questions, dossiers déposés et adoptés, votes, thèmes dominants.</p></div>
      ${D.syntheses.map((s) => `${syntheseFeature(s, true)}${themeBars(s)}`).join("") || '<p class="empty">Pas encore de synthèse.</p>'}`;
  }

  function renderFwb() {
    const lim = ui.limit.fwb || PAGE;
    view.innerHTML = `<div class="page-head"><h1>Fédération Wallonie-Bruxelles</h1><p class="lede">Derniers documents publiés par le Parlement de la Fédération Wallonie-Bruxelles, accumulés à chaque mise à jour.</p></div>
      <div class="rows">${D.fwb.slice(0, lim).map((f) => `<div class="row"><div class="row-meta">${parlBadge("fwb")}<span class="num">${fdate(f.date)}</span></div>
        <div class="row-main">${f.url ? `<a class="row-title" href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.titre)}</a>` : `<span class="row-title">${esc(f.titre)}</span>`}
        <span class="row-sub">${esc(f.type)}${f.groupes && f.groupes.length ? " · " + esc(f.groupes.join(", ")) : ""}</span>${chips(f.themes)}</div><div class="row-side">${radarMark(f)}</div></div>`).join("") || '<p class="empty">Pas encore de document collecté.</p>'}</div>
      ${moreButton("fwb", Math.min(lim, D.fwb.length), D.fwb.length)}`;
  }

  function renderSuivis() {
    const ids = storeGet();
    const ds = ids.map((i) => byId.d.get(i)).filter(Boolean);
    const es = ids.map((i) => byId.e.get(i)).filter(Boolean);
    view.innerHTML = `<div class="page-head"><h1>Mes suivis</h1><p class="lede">Les dossiers et élus que vous suivez, enregistrés dans ce navigateur uniquement.</p></div>
      <section class="block"><h2>Dossiers</h2><div class="rows">${ds.map(dossierRow).join("") || '<p class="empty">Aucun dossier suivi. Ouvrez un dossier et cliquez sur « Suivre ».</p>'}</div></section>
      <section class="block"><h2>Élus</h2>${es.length ? `<div class="cards">${es.map((d) => `<a class="card" href="#e.${esc(d.id)}">${d.photo ? `<img src="${esc(d.photo)}" alt="" loading="lazy">` : '<span class="avatar"></span>'}<span><span class="who">${esc(d.nom_complet)}</span><br><span class="party-line">${esc(d.parti)}</span></span></a>`).join("")}</div>` : '<p class="empty">Aucun élu suivi.</p>'}</section>
      <p class="muted">Pour être prévenu sans ouvrir le site, abonnez votre lecteur de flux ou Outlook au <a href="data/flux-radar.xml">flux du radar PME</a>.</p>`;
  }

  function renderMethode() {
    const src = D.meta.sources || {};
    const names = { wallonie_thesaurus: "Wallonie · thésaurus des matières", wallonie_deputes: "Wallonie · députés (open data)", wallonie_questions: "Wallonie · questions et interpellations",
      wallonie_dossiers: "Wallonie · dossiers législatifs", wallonie_votes: "Wallonie · votes nominatifs (comptes rendus)", bruxelles_questions: "Bruxelles · questions",
      bruxelles_dossiers: "Bruxelles · dossiers législatifs", fwb_documents: "FWB · derniers documents" };
    const P = D.prompts || {};
    view.innerHTML = `<div class="page-head"><h1>Méthode et transparence</h1><p class="lede">D'où viennent les données, comment elles sont mises à jour, et ce que fait l'IA.</p></div>
      <section class="block"><h2>Sources et fraîcheur</h2><div class="table-wrap"><table><thead><tr><th>Source</th><th>État</th><th class="n">Éléments</th><th>Dernière mise à jour</th></tr></thead><tbody>
        ${Object.entries(src).map(([k, s]) => `<tr><td>${esc(names[k] || k)}</td><td>${s.ok ? '<span class="status-ok">OK</span>' : `<span class="status-ko" title="${esc(s.erreur || "")}">En échec</span>`}</td><td class="n">${s.n == null ? "–" : nf(s.n)}</td><td>${s.maj ? fdate(s.maj) + " " + s.maj.slice(11, 16) + " UTC" : "–"}</td></tr>`).join("")}
      </tbody></table></div></section>
      <section class="prose"><h2>Ce qui est couvert</h2><ul>
        <li><b>Parlement de Wallonie</b> : données ouvertes (députés, publications), questions écrites, orales, d'actualité et urgentes, interpellations, dossiers législatifs avec chronologie, votes nominatifs relevés dans les comptes rendus intégraux des séances plénières.</li>
        <li><b>Parlement bruxellois et Assemblée réunie (COCOM)</b> : questions, interpellations et demandes d'explications ; dossiers législatifs avec chronologie, date de vote et de publication.</li>
        <li><b>Parlement de la Fédération Wallonie-Bruxelles</b> : derniers documents publiés, accumulés au fil des mises à jour.</li>
        <li><b>Non couverts pour l'instant</b> : Chambre, Parlement flamand et Parlement de la Communauté germanophone. Leurs sites refusent les accès automatisés, et la veille ne contourne pas ces protections.</li>
      </ul>
      <h2>Classement par thème et radar</h2>
      <p>Chaque élément est classé par mots-clés de l'intitulé et, pour les questions écrites wallonnes, par la matière officielle attribuée par le Parlement. Le radar PME &amp; indépendants repère les éléments qui touchent directement les entreprises, l'emploi et la formation. Les listes de mots-clés sont modifiables dans <span class="ref">config/themes.json</span>.</p>
      <h2>Votes</h2>
      <p>Les votes sont lus dans les comptes rendus PDF. Une liste de noms n'est rattachée à un vote que si son effectif correspond exactement au décompte officiel ; sinon seuls les décomptes sont affichés. Un « vote contre la ligne » est un vote différent de la position majoritaire du groupe.</p>
      <h2>Transparence IA</h2>
      <p>Les résumés de dossiers et les synthèses mensuelles sont rédigés par ${esc(P.modele || "un modèle Claude d'Anthropic")}. Le modèle reçoit l'intitulé officiel, les étapes de la procédure et les ${nf(P.extrait_max || 15000)} premiers caractères du document déposé. Il ne voit pas le reste du document : un résumé peut donc manquer un élément du dispositif ou un amendement. Chaque résumé est daté et renvoie au texte officiel, qui fait foi. Les consignes complètes données au modèle sont reproduites ci-dessous.</p>
      ${P.resume_dossier ? `<h3>Consigne · résumé de dossier</h3><pre class="prompt">${esc(P.resume_dossier)}</pre>` : ""}
      ${P.synthese_mensuelle ? `<h3>Consigne · synthèse mensuelle</h3><pre class="prompt">${esc(P.synthese_mensuelle)}</pre>` : ""}
      </section>`;
  }

  function notFound() {
    view.innerHTML = '<div class="page-head"><h1>Élément introuvable</h1><p class="lede">Il a peut-être été retiré lors de la dernière mise à jour. <a href="#accueil">Retour à l’accueil</a></p></div>';
  }

  // ------------------------------------------------------------ navigation
  let lastFocus = null;
  function keepFocus() {
    if (lastFocus) {
      const el = document.getElementById(lastFocus.id);
      if (el) {
        el.focus();
        if (el.setSelectionRange && lastFocus.pos != null) { try { el.setSelectionRange(lastFocus.pos, lastFocus.pos); } catch (e) { /* select */ } }
      }
    }
  }
  document.addEventListener("focusin", (ev) => {
    const t = ev.target;
    if (t && t.id && view.contains(t)) lastFocus = { id: t.id, pos: t.selectionStart };
  });
  document.addEventListener("input", (ev) => { const t = ev.target; if (t && t.id) lastFocus = { id: t.id, pos: t.selectionStart }; });

  view.addEventListener("click", (ev) => {
    const more = ev.target.closest("[data-more]");
    if (more) {
      const name = more.dataset.more;
      ui.limit[name] = (ui.limit[name] || (name.startsWith("elu-") ? 20 : PAGE)) + PAGE;
      lastFocus = null;
      route(true);
      return;
    }
    const f = ev.target.closest("[data-follow]");
    if (f) {
      const id = f.dataset.follow;
      const list = storeGet();
      const i = list.indexOf(id);
      if (i >= 0) list.splice(i, 1); else list.push(id);
      storeSet(list);
      const on = list.includes(id);
      f.setAttribute("aria-pressed", String(on));
      f.textContent = on ? "Suivi" : "Suivre";
    }
  });

  function route(keepScroll) {
    const h = decodeURIComponent((location.hash || "#accueil").slice(1));
    const [kind, ...rest] = h.split(".");
    const id = rest.join(".");
    const section = { d: "dossiers", v: "votes", e: "elus" }[kind] || kind;
    document.querySelectorAll("#nav a").forEach((a) => { if (a.dataset.r === section) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    const y = window.scrollY;
    if (!keepScroll) lastFocus = null;
    const r = { accueil: renderHome, dossiers: renderDossiers, questions: renderQuestions, votes: renderVotes, elus: renderElus,
      syntheses: renderSyntheses, fwb: renderFwb, suivis: renderSuivis, methode: renderMethode }[kind];
    const done = () => { if (keepScroll) window.scrollTo(0, y); else window.scrollTo(0, 0); };
    if (kind === "d") { renderDossier(id); done(); } else if (kind === "v") { renderVote(id); done(); } else if (kind === "e") { renderElu(id).then(done); } else if (r) { const p = r(); if (p && p.then) p.then(done); else done(); } else { renderHome(); done(); }
  }

  // une photo officielle indisponible laisse place au cadre vide plutôt qu'à une image cassée
  document.addEventListener("error", (ev) => {
    const t = ev.target;
    if (t && t.tagName === "IMG") { t.removeAttribute("src"); t.classList.add("avatar"); t.alt = ""; }
  }, true);

  async function start() {
    const [meta, dossiers, votes, deputes, syntheses, fwb, resumes, prompts, recentes] = await Promise.all([
      getJSON("meta.json", null), getJSON("dossiers.json", []), getJSON("votes.json", []), getJSON("deputes.json", []),
      getJSON("syntheses.json", []), getJSON("fwb.json", []), getJSON("resumes.json", {}), getJSON("prompts.json", null),
      getJSON("questions-recentes.json", []),
    ]);
    if (!meta) {
      view.innerHTML = '<div class="page-head"><h1>Données absentes</h1><p class="lede">Le dossier <span class="ref">data/</span> est vide. Lancez <span class="ref">python3 collect/build.py</span> puis rechargez la page.</p></div>';
      return;
    }
    Object.assign(D, { meta, dossiers, votes, deputes, syntheses, fwb, resumes, prompts, recentes });
    D.dossiers.forEach((d) => { d._s = fold([d.titre, d.num, d.auteurs, d.commission].join(" ")); byId.d.set(d.id, d); });
    D.votes.forEach((v) => { v._s = fold([v.objet, (v.docs || []).join(" "), v.seance].join(" ")); byId.v.set(v.id, v); });
    D.deputes.forEach((e) => byId.e.set(e.id, e));
    document.getElementById("fresh").textContent = "Mis à jour le " + fdate(meta.genere_le) + " à " + meta.genere_le.slice(11, 16) + " UTC";
    window.addEventListener("hashchange", () => route(false));
    route(false);
  }
  start();
})();
