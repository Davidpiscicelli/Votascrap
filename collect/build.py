"""Mise à jour complète des données du site.

    python3 veille/collect/build.py            # tout
    python3 veille/collect/build.py --sans-votes   # sans relire les PDF de séance (plus rapide)

Chaque source est indépendante : si l'une échoue, les données précédentes sont conservées.
"""

import argparse
import os
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import date, timedelta
from xml.sax.saxutils import escape

import bruxelles
import fwb
import wallonie
from classify import Classifier
from common import ROOT, SITE, data_path, fold, load_config, log, now_iso, read_json, write_json

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def letters(s):
    return re.sub(r"[^a-z]", "", fold(s))


class Status:
    def __init__(self):
        self.sources = read_json(data_path("meta.json"), {}).get("sources", {})

    def run(self, key, fn, fallback):
        try:
            res = fn()
            self.sources[key] = {"ok": True, "maj": now_iso(), "n": len(res[0] if isinstance(res, tuple) else res)}
            return res
        except Exception as e:  # noqa: BLE001 - une source en panne ne bloque pas les autres
            traceback.print_exc()
            log(f"{key}: ÉCHEC ({e}) — données précédentes conservées")
            prev = self.sources.get(key, {})
            self.sources[key] = dict(prev, ok=False, erreur=str(e)[:300], tentative=now_iso())
            return fallback


def index_deputes(deps):
    idx = {}
    for d in deps:
        for k in (letters(d["prenom"] + d["nom"]), letters(d["nom"] + d["prenom"])):
            idx[k] = d
    return idx


def tag_all(items, clf, fields):
    for it in items:
        it["themes"], it["radar"] = clf.tag(*(it.get(f) or "" for f in fields), mat=it.get("mat"))


def positions_par_parti(v):
    pp = defaultdict(lambda: {"oui": 0, "non": 0, "abst": 0})
    for k in ("oui", "non", "abst"):
        for n in v["noms"][k]:
            pp[n["parti"]][k] += 1
    return dict(pp)


def compact_votes(votes, idx):
    """Votes : positions nominatives (id d'élu si connu), lignes de parti et dissidences."""
    out = []
    for v in votes:
        if not (v["pour"] or v["contre"] or v["abstention"]):
            continue  # scrutin secret ou décompte illisible
        pp = positions_par_parti(v)
        ligne = {p: max(c, key=c.get) for p, c in pp.items() if sum(c.values()) >= 2}
        pos, dissidents = [], []
        for k in ("oui", "non", "abst"):
            for n in v["noms"][k]:
                dep = idx.get(letters(n["nom"]))
                who = dep["id"] if dep else n["nom"]
                pos.append([who, k[0], n["parti"]])
                if n["parti"] in ligne and ligne[n["parti"]] != k:
                    dissidents.append(who)
        out.append({k: v[k] for k in ("id", "parl", "date", "seance", "objet", "nature", "docs", "resultat",
                                       "resultat_deduit", "votants", "pour", "contre", "abstention", "url",
                                       "themes", "radar") if k in v}
                   | {"partis": pp, "ligne": ligne, "positions": pos, "dissidents": dissidents})
    return out


def stats_deputes(deps, questions, votes, idx):
    by_id = {d["id"]: d for d in deps}
    for d in deps:
        d.update(questions=0, votes=0, dissidences=0, themes=Counter())
    for q in questions:
        if q["parl"] != "wal":
            continue
        dep = idx.get(letters(q["auteur"]))
        if dep:
            q["auteur_id"], q["parti"] = dep["id"], dep["parti"]
            dep["questions"] += 1
            dep["themes"].update(q["themes"])
    for v in votes:
        for who, _, _ in v["positions"]:
            if who in by_id:
                by_id[who]["votes"] += 1
        for who in v["dissidents"]:
            if who in by_id:
                by_id[who]["dissidences"] += 1
    for d in deps:
        d["themes"] = [t for t, _ in d["themes"].most_common(4)]
        d.pop("key", None)
    return deps


def link_votes_dossiers(dossiers, votes):
    by_id = {d["id"]: d for d in dossiers}
    for d in dossiers:
        d["votes"] = []
    for v in votes:
        v["dossier"] = None
        for ref in v.get("docs", []):
            num, a, b = ref.split("-")
            d = by_id.get(f"wal-{num}-{a}-{b}")
            if d:
                v["dossier"] = d["id"]
                d["votes"].append(v["id"])
                v["themes"] = sorted(set(v.get("themes", [])) | set(d.get("themes", [])))
                v["radar"] = v.get("radar") or d.get("radar")
                break


def date_adoption(d):
    if d["statut"] != "adopté":
        return None
    if d.get("date_vote"):
        return d["date_vote"]
    for e in d.get("etapes", []):
        if "adopte" in fold(e["libelle"]) and "seance" in fold(e["libelle"]) or e.get("t") in ("49", "92"):
            return e["date"]
    return d.get("date_maj")


def syntheses(questions, dossiers, votes, labels, n_mois=12):
    mois = sorted({(q["date"] or "")[:7] for q in questions if q["date"]}, reverse=True)[:n_mois]
    resumes_ia = read_json(data_path("syntheses_ia.json"), {})
    out = []
    for m in mois:
        qs = [q for q in questions if (q["date"] or "").startswith(m)]
        dep = [d for d in dossiers if (d.get("date_depot") or "").startswith(m)]
        ado = [d for d in dossiers if (date_adoption(d) or "").startswith(m)]
        vs = [v for v in votes if (v["date"] or "").startswith(m)]
        th = Counter(t for q in qs for t in q["themes"])
        y, mm = m.split("-")
        out.append({
            "mois": m,
            "libelle": f"{MOIS[int(mm) - 1]} {y}",
            "questions": dict(Counter(q["parl"] for q in qs)),
            "questions_radar": sum(q["radar"] for q in qs),
            "themes": [[labels.get(t, t), n] for t, n in th.most_common(6)],
            "dossiers_deposes": [d["id"] for d in dep],
            "dossiers_adoptes": [d["id"] for d in ado],
            "votes": len(vs),
            "votes_divises": sum(1 for v in vs if v["contre"] > 0),
            "texte_ia": resumes_ia.get(m),
        })
    return out


def compact_questions(qs):
    """Questions allégées : la fonction des ministres va dans ministres.json et le site reconstruit
    l'URL officielle à partir de l'identifiant (voir questionUrl dans site/app.js)."""
    keys = ["id", "parl", "type", "date", "auteur", "auteur_id", "parti", "destinataire", "num",
            "titre", "themes", "radar", "assemblee", "publie"]
    return [{k: q[k] for k in keys if q.get(k) not in (None, "", [], False)} for q in qs]


def ministres(qs):
    """{destinataire: fonction la plus récente}."""
    out = {}
    for q in sorted(qs, key=lambda q: q["date"] or ""):
        if q.get("destinataire") and q.get("fonction"):
            out[q["destinataire"]] = q["fonction"]
    return out


def prompts_publics():
    """Consignes IA publiées telles quelles sur la page « Méthode »."""
    out = {"modele": SITE["ia"]["modele"], "extrait_max": 15000}
    for name in ("resume_dossier", "synthese_mensuelle"):
        try:
            with open(os.path.join(ROOT, "prompts", name + ".md"), encoding="utf-8") as f:
                out[name] = f.read().strip()
        except FileNotFoundError:
            pass
    return out


def flux_radar(dossiers, questions, base_url, n=60):
    """Flux Atom du radar PME (dossiers et questions), pour Outlook ou un lecteur de flux."""
    items = [(d.get("date_maj") or "", d["titre"], f"{base_url}#d.{d['id']}", f"{d['type']} · {d['statut']}", d["id"])
             for d in dossiers if d.get("radar")]
    items += [(q["date"] or "", q["titre"], q.get("url") or base_url, f"{q['type']} · {q['auteur']} → {q.get('destinataire', '')}", q["id"])
              for q in questions if q.get("radar")]
    items.sort(reverse=True)
    entries = "".join(
        f"<entry><id>urn:pleniere:{escape(i)}</id><title>{escape(t)}</title><link href=\"{escape(u)}\"/>"
        f"<updated>{d or '2000-01-01'}T00:00:00Z</updated><summary>{escape(s)}</summary></entry>"
        for d, t, u, s, i in items[:n])
    return ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
            f"<title>{escape(SITE['nom'])} · Radar PME &amp; indépendants</title><id>urn:pleniere:radar</id>"
            f"<link href=\"{escape(base_url)}\"/><updated>{now_iso()}</updated>{entries}</feed>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sans-votes", action="store_true", help="ne relit pas les comptes rendus PDF")
    args = ap.parse_args()

    st = Status()
    prev_dossiers = {d["id"]: d for d in read_json(data_path("dossiers.json"), [])}
    prev_questions = read_json(data_path("questions.json"), [])
    prev_votes = read_json(data_path("votes.json"), [])
    prev_fwb = read_json(data_path("fwb.json"), [])

    def prev(parl, items):
        return [x for x in items if x.get("parl") == parl]

    cats, noms_mat = st.run("wallonie_thesaurus", wallonie.matieres, ({}, {})) if SITE["wallonie"]["actif"] else ({}, {})
    clf = Classifier(matieres=cats)

    deps, q_wal, d_wal, v_wal = [], [], [], []
    if SITE["wallonie"]["actif"]:
        deps = st.run("wallonie_deputes", wallonie.deputes, read_json(data_path("deputes.json"), []))
        q_wal = st.run("wallonie_questions", wallonie.questions, prev("wal", prev_questions))
        d_wal = st.run("wallonie_dossiers", lambda: wallonie.dossiers(prev_dossiers), prev("wal", list(prev_dossiers.values())))
        if not args.sans_votes:
            v_wal = st.run("wallonie_votes", wallonie.votes, None)
    q_bxl, d_bxl = [], []
    if SITE["bruxelles"]["actif"]:
        q_bxl = st.run("bruxelles_questions", bruxelles.questions, prev("bxl", prev_questions))
        d_bxl = st.run("bruxelles_dossiers", lambda: bruxelles.dossiers(prev_dossiers), prev("bxl", list(prev_dossiers.values())))
    docs_fwb = prev_fwb
    if SITE["fwb"]["actif"]:
        new = st.run("fwb_documents", fwb.documents_recents, [])
        seen = {d["id"] for d in new}
        docs_fwb = sorted(new + [d for d in prev_fwb if d["id"] not in seen], key=lambda d: d["date"] or "", reverse=True)[:3000]

    questions = q_wal + q_bxl
    dossiers = d_wal + d_bxl
    tag_all(questions, clf, ["titre"])
    tag_all(dossiers, clf, ["titre", "commission"])
    tag_all(docs_fwb, clf, ["titre", "type"])
    for q in questions:
        if q.get("mat") and q["mat"] in noms_mat:
            q["matiere"] = noms_mat[q["mat"]]

    idx = index_deputes(deps)
    if v_wal is None:  # échec de lecture des votes : on garde les précédents
        votes = prev_votes
    elif v_wal:
        tag_all(v_wal, clf, ["objet"])
        votes = compact_votes(v_wal, idx)
    else:
        votes = prev_votes
    link_votes_dossiers(dossiers, votes)
    deps = stats_deputes(deps, questions, votes, idx)

    labels = dict(clf.labels)
    themes_cfg = load_config("themes.json")
    meta = {
        "genere_le": now_iso(),
        "site": {k: SITE[k] for k in ("nom", "sous_titre", "accroche")},
        "themes": [{"id": t, "label": l} for t, l in labels.items()],
        "radar": {k: themes_cfg.get("radar", {}).get(k) for k in ("label", "description")},
        "sources": st.sources,
        "compteurs": {
            "questions": dict(Counter(q["parl"] for q in questions)),
            "dossiers": dict(Counter(d["parl"] for d in dossiers)),
            "votes": len(votes),
            "deputes": len(deps),
            "fwb": len(docs_fwb),
        },
    }
    write_json(data_path("questions.json"), compact_questions(sorted(questions, key=lambda q: q["date"] or "", reverse=True)))
    write_json(data_path("dossiers.json"), sorted(dossiers, key=lambda d: d.get("date_maj") or "", reverse=True))
    write_json(data_path("votes.json"), sorted(votes, key=lambda v: v["date"] or "", reverse=True))
    write_json(data_path("deputes.json"), deps)
    write_json(data_path("fwb.json"), docs_fwb)
    write_json(data_path("syntheses.json"), syntheses(questions, dossiers, votes, labels))
    depuis = (date.today() - timedelta(days=60)).isoformat()
    write_json(data_path("questions-recentes.json"),
               compact_questions(sorted((q for q in questions if (q["date"] or "") >= depuis), key=lambda q: q["date"], reverse=True)))
    write_json(data_path("prompts.json"), prompts_publics())
    write_json(data_path("ministres.json"), ministres(questions))
    with open(data_path("flux-radar.xml"), "w", encoding="utf-8") as f:
        f.write(flux_radar(dossiers, questions, SITE.get("url_publique", "")))
    write_json(data_path("meta.json"), meta, compact=False)
    log("terminé :", meta["compteurs"])
    ko = [k for k, s in st.sources.items() if not s.get("ok", True)]
    if ko:
        log("ATTENTION sources en échec (données précédentes conservées) :", ", ".join(ko))
    return 0


if __name__ == "__main__":
    sys.exit(main())
