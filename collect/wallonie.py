"""Parlement de Wallonie.

Sources (toutes publiques) :
- Open data JSON : https://www.parlement-wallonie.be/opendata/ (députés, publications)
- Moteur « Travail parlementaire » : listes de questions/interpellations et de dossiers (HTML)
- Comptes rendus intégraux (CRI, PDF) : votes nominatifs en séance plénière
"""

import html
import os
import re
import shutil
import subprocess
import tempfile

from common import (clean, date_fr, fetch, fetch_json, fold, log, name_key, nom_lisible, noms_lisibles,
                    read_json, cache_path, write_json, SITE)

BASE = "https://www.parlement-wallonie.be"
OD = BASE + "/opendata"
CFG = SITE["wallonie"]
LEG = CFG["legislature_id"]


# ---------------------------------------------------------------- députés

def deputes():
    d = fetch_json(f"{OD}/composition_dep_od.php?f=json")
    out = []
    for x in d["deputes"]:
        out.append({
            "id": f"wal-{x['dep_id']}",
            "parl": "wal",
            "nom": clean(x["dep_nom"]),
            "prenom": clean(x["dep_prenom"]),
            "nom_complet": f"{clean(x['dep_prenom'])} {clean(x['dep_nom']).title()}",
            "parti": clean(x["dep_parti"]),
            "circonscription": clean(x["dep_circons"]),
            "photo": x.get("dep_photo"),
            "url": f"{BASE}/pwpages?p=composition_dep&id={x['dep_id']}",
            "key": name_key(f"{x['dep_prenom']} {x['dep_nom']}"),
        })
    return out


# ---------------------------------------------------------------- thésaurus

def matieres():
    """{mat_id: rubrique} et {mat_id: libellé} du thésaurus officiel."""
    h = fetch(f"{BASE}/ajax?p=matieres")
    cat, cats, noms = None, {}, {}
    rx = re.compile(r"<h3><a href='#'+>(.*?)</a></h3>|mat_id\.value=&quot;(\d+)&quot;;"
                    r"document\.rech\.mat_nom\.value=&quot;(.*?)&quot;", re.S)
    for m in rx.finditer(h):
        if m.group(1):
            cat = html.unescape(m.group(1)).strip()
        else:
            cats[m.group(2)] = cat
            noms[m.group(2)] = re.sub(r"\s+\d+$", "", html.unescape(m.group(3)).strip())
    return cats, noms


# ---------------------------------------------------------------- questions

Q_ROW = re.compile(
    r"<!--SDOC : (?P<sdoc>\d+) DOCTYPE : (?P<type>\d+) MAT ID : (?P<mat>\d*) AUTEUR ID : (?P<aut>\d*) "
    r"DESTI ID : (?P<dest>\d*)-->.*?</span> du <span class=\"text-pw-date\">(?P<date>[\d/]+)</span>"
    r"(?P<who>.*?)</p>.*?iddoc=(?P<iddoc>\d+)\">(?P<titre>.*?)</a>", re.S)


def parse_questions(h, type_label):
    out = []
    for m in Q_ROW.finditer(h):
        who = clean(m.group("who"))
        num = None
        mnum = re.search(r"\((\d+) \((\d{4}-\d{4}|se\d{4})\)[^)]*?(?:échéance : ([\d/]+))?\)\s*$", who)
        if mnum:
            num = f"{mnum.group(1)} ({mnum.group(2)})"
            who = who[:mnum.start()].strip()
        who = re.sub(r"^de\s+", "", who)
        auteur, _, dest = who.partition(" à ")
        ministre, _, fonction = dest.partition(",")
        titre = clean(m.group("titre"))
        out.append({
            "id": f"wal-q-{m.group('iddoc')}",
            "parl": "wal",
            "type": type_label,
            "date": date_fr(m.group("date")),
            "auteur": noms_lisibles(auteur),
            "destinataire": nom_lisible(ministre.strip()),
            "fonction": fonction.strip(),
            "num": num,
            "titre": titre[:1].upper() + titre[1:],
            "mat": m.group("mat") or None,
            "url": f"{BASE}/pwpages?p=interp-questions-voir&type={m.group('type')}&iddoc={m.group('iddoc')}",
        })
    return out


def questions():
    out = []
    for tid, label in CFG["types_questions"].items():
        url = f"{BASE}/pwpages?p=interp-questions-recherche&idleg={LEG}&type={tid}"
        h = fetch(url, timeout=300)
        qs = [q for q in parse_questions(h, label) if q["date"] and q["date"] >= CFG["date_min_questions"]]
        log(f"wallonie: {len(qs)} × {label}")
        out += qs
    return out


def question_detail(url):
    """Texte de la question et, s'il est publié, de la réponse."""
    h = fetch(url)
    items = re.findall(r'<li class="list-group-item">(.*?)</li>', h, re.S)
    res = {}
    for it in items:
        head = clean(re.search(r"<h5>(.*?)</h5>", it, re.S).group(1)) if "<h5>" in it else ""
        body = clean(re.sub(r"<h5>.*?</h5>|<ul>.*?</ul>", "", it, flags=re.S))
        if "réponse" in head.lower():
            res["reponse"] = body[:6000]
            res["date_reponse"] = date_fr(re.search(r"([\d/]{10})", head).group(1)) if re.search(r"([\d/]{10})", head) else None
        elif "question" in head.lower() and "question" not in res:
            res["question"] = body[:6000]
    return res


# ---------------------------------------------------------------- dossiers

D_ROW = re.compile(r"<!--SDOC : \d+ DOCTYPE : (?P<type>\d+).*?iddoc=(?P<iddoc>\d+)\">(?P<titre>.*?)</a></h5>"
                   r".*?Dossier n° (?P<num>\d+) \((?P<ses>[^)]+)\).*?comprenant (?P<n>\d+) document", re.S)

DOSSIER_TYPES = {"1": "Projet de décret", "3": "Proposition de décret", "94": "Proposition de résolution"}


def liste_dossiers():
    out = []
    for t in ("alldecbud", "94"):
        h = fetch(f"{BASE}/pwpages?p=doc-recherche&idleg={LEG}&type={t}", timeout=300)
        for m in D_ROW.finditer(h):
            out.append({"iddoc": m.group("iddoc"), "type_code": m.group("type"), "titre": clean(m.group("titre")),
                        "num": m.group("num"), "session": m.group("ses"), "n_docs": int(m.group("n"))})
    log(f"wallonie: {len(out)} dossiers")
    return out


STEP = re.compile(r'<li class="list-group-item"><!--SDOC ID : \d+ SDOC ID TYPE : (?P<t>\d+).*?-->'
                  r'<span class="text-pw-date">(?P<date>[\d/]+)</span><h5>(?P<h>.*?)</h5>(?P<rest>.*?)</li>', re.S)


def parse_dossier_detail(h):
    etapes = []
    for m in STEP.finditer(h):
        head = m.group("h")
        auteurs = ""
        ma = re.search(r'<span class="text-pw-lightblue">\s*de (.*?)</span>', head, re.S)
        if ma:
            auteurs = noms_lisibles(clean(ma.group(1)))
            head = head[:ma.start()]
        lien = re.search(r'href="(http[^"]+\.pdf)"[^>]*>(.*?)</a>', m.group("rest"), re.S)
        etapes.append({
            "t": m.group("t"),
            "date": date_fr(m.group("date")),
            "libelle": clean(head),
            "auteurs": auteurs,
            "doc": clean(lien.group(2)).replace(" (PDF)", "") if lien else None,
            "url": lien.group(1).replace("http://", "https://") if lien else None,
        })
    return etapes


def statut_dossier(etapes):
    libs = " | ".join(fold(e["libelle"]) for e in etapes)
    types = {e["t"] for e in etapes}
    if types & {"92", "49"} or "texte adopte en seance pleniere" in libs:
        return "adopté"
    if "rejet" in libs:
        return "rejeté"
    if "retire" in libs:
        return "retiré"
    if types & {"123", "138"}:
        return "rapport de commission"
    if types & {"85", "54", "99", "126", "117"} or "envoi en commission" in libs:
        return "en commission"
    return "déposé"


def dossiers(previous):
    """Dossiers législatifs avec chronologie. `previous` : {id: dossier} de l'exécution précédente."""
    out = []
    for d in liste_dossiers():
        did = f"wal-{d['num']}-{d['session']}"
        old = previous.get(did)
        if old and old.get("n_docs") == d["n_docs"] and old.get("etapes"):
            etapes = old["etapes"]
        else:
            etapes = parse_dossier_detail(fetch(f"{BASE}/pwpages?p=doc-recherche-det&iddoc={d['iddoc']}"))
        for e in etapes:  # aussi pour les chronologies reprises de l'exécution précédente
            e["auteurs"] = noms_lisibles(e.get("auteurs", ""))
        commission = next((re.sub(r"^Envoi en ", "", e["libelle"]) for e in etapes
                           if fold(e["libelle"]).startswith("envoi en commission")), None)
        if not commission:
            commission = next((re.sub(r"^.*au nom de la ", "", e["libelle"]) for e in etapes
                               if "au nom de la commission" in fold(e["libelle"])), None)
        depot = etapes[0] if etapes else {}
        dates = [e["date"] for e in etapes if e["date"]]
        out.append({
            "id": did,
            "parl": "wal",
            "num": f"{d['num']} ({d['session']})",
            "type": DOSSIER_TYPES.get(d["type_code"], depot.get("libelle") or "Dossier"),
            "titre": d["titre"],
            "auteurs": depot.get("auteurs", ""),
            "date_depot": min(dates) if dates else None,
            "date_maj": max(dates) if dates else None,
            "statut": statut_dossier(etapes),
            "commission": commission.strip(" .") if commission else None,
            "n_docs": d["n_docs"],
            "etapes": etapes,
            "url": f"{BASE}/pwpages?p=doc-recherche-det&iddoc={d['iddoc']}",
            "pdf": depot.get("url"),
        })
    return out


# ---------------------------------------------------------------- votes nominatifs

HEADER = re.compile(r"^(PW\s*[–-]\s*Session .*|P\.W\.\s*[–-].*|\d{1,3}|Votes? nominatifs?|\(Suite\))$")
DOCREF = re.compile(r"(?:Doc\.|[Dd]ocument n°)\s*(\d+)\s*\((\d{4})-?(\d{4})\)")
LIST_HEAD = re.compile(r"-\s*(Ont répondu oui|A répondu oui|Ont répondu non|A répondu non|"
                       r"Se sont abstenu(?:e)?s|S[’']est abstenu(?:e)?)\s*:", re.I)


def _flow(txt):
    """Texte continu : en-têtes de page retirés, césures recollées."""
    lines = []
    for line in txt.splitlines():
        s = line.strip()
        if not s or HEADER.match(s):
            continue
        lines.append(s)
    out = ""
    for s in lines:
        if out.endswith("-") and not out.endswith(" -"):
            out += s
        else:
            out += (" " if out else "") + s
    return out


PARTICULES = {"de", "du", "des", "van", "von", "der", "den", "le", "la", "d'", "d’", "di", "da"}
NON_PARTIS = {"suite", "applaudissements", "rires", "reaction", "réaction", "exclamations", "interruption"}
PARTIS_CONNUS = {"MR", "PS", "PTB", "Ecolo", "Les Engagés", "cdH", "DéFI", "Indépendant", "Indépendante",
                 "Groen", "Vooruit", "N-VA", "Open Vld", "CD&V", "Vlaams Belang", "Team Fouad Ahidar", "Anders"}


def _partis(flow):
    """Partis cités au moins 3 fois entre parenthèses (« Nom (Parti) »)."""
    cnt = {}
    for p in re.findall(r"\(([^()\d]{2,25})\)", flow):
        p = p.strip()
        if p[:1].isupper() and len(p.split()) <= 3 and fold(p.split()[0]) not in NON_PARTIS:
            cnt[p] = cnt.get(p, 0) + 1
    return {p for p, n in cnt.items() if n >= 3} | PARTIS_CONNUS


def _names(chunk, partis):
    """« Prénom Nom (Parti) » dont le parti est connu ; la prose intercalée est ignorée."""
    res, last = [], 0
    for m in re.finditer(r"\(([^()]{1,30})\)", chunk):
        parti = m.group(1).strip()
        seg = chunk[last:m.start()]
        last = m.end()
        if parti not in partis or re.match(r"\.\s*[–-]", chunk[m.end():m.end() + 4]):
            continue  # parti inconnu, ou prise de parole « Mme X (PS). – »
        nom = []
        for w in reversed(seg.split()):
            # un mot ponctué (« Roberty. », « MM. », « Mme, ») ou en minuscules clôt le nom
            if w[-1] in ".,;:)" or not (w[:1].isupper() or w.lower() in PARTICULES) or len(nom) >= 5:
                break
            nom.insert(0, w)
        if len(nom) >= 2:
            res.append({"nom": " ".join(nom), "parti": parti})
    return res


VOTE_MARK = re.compile(
    r"-\s*Il est procédé au vote nominatif\.\s*"
    r"(?:(?P<tot>\d+) membres? prenn?ent part au vote\.\s*)?"
    r"(?:(?P<oui>\d+) membres? répond(?:ent)? oui\.\s*)?"
    r"(?:(?P<non>\d+) membres? répond(?:ent)? non\.\s*)?"
    r"(?:(?P<abst>\d+) membres? s[’']abst\w+\.\s*)?"
    r"(?:En conséquence,(?P<res>.{0,250}?)\.)?")
DECOMPTE = re.compile(
    r"(?P<tot>\d+) membres? prenn?ent part au vote\.\s*"
    r"(?:(?P<oui>\d+) membres? répond(?:ent)? oui\.\s*)?"
    r"(?:(?P<non>\d+) membres? répond(?:ent)? non\.\s*)?"
    r"(?:(?P<abst>\d+) membres? s[’']abst\w+\.\s*)?")
OBJET = re.compile(r"(Nous (?:allons|passons|procédons)[^.]{0,40}?vot|Je mets aux voix|Je soumets au vote)", re.I)


def _lists(flow):
    """Listes nominatives (oui / non / abstention) dans l'ordre du document."""
    heads = list(LIST_HEAD.finditer(flow))
    partis = _partis(flow)
    out = []
    for j, h in enumerate(heads):
        lab = h.group(1).lower()
        key = "oui" if "oui" in lab else "non" if "non" in lab else "abst"
        stop = heads[j + 1].start() if j + 1 < len(heads) else len(flow)
        chunk = flow[h.end():stop]
        cut = re.search(r"En conséquence|- Il est procédé|Justification d", chunk)
        out.append({"key": key, "names": _names(chunk[:cut.start()] if cut else chunk[:6000], partis),
                    "used": False})
    return out


def _match_lists(lists, tot, state, window=10):
    """Rattache à un vote les listes libres dont le type et l'effectif correspondent aux décomptes.

    La recherche part du dernier vote rattaché (state["ptr"]), avec une petite marge arrière car
    les colonnes peuvent intervertir deux listes voisines. Sans correspondance exacte, aucun nom.
    """
    lo = max(0, state["ptr"] - 8)
    picked = {}
    for key in ("oui", "non", "abst"):
        if not tot[key]:
            continue
        for i in range(lo, min(len(lists), state["ptr"] + window)):
            l = lists[i]
            if not l["used"] and l["key"] == key and len(l["names"]) == tot[key] and i not in picked.values():
                picked[key] = i
                break
        else:
            return {"oui": [], "non": [], "abst": []}
    noms = {"oui": [], "non": [], "abst": []}
    for key, i in picked.items():
        lists[i]["used"] = True
        noms[key] = lists[i]["names"]
    if picked:
        state["ptr"] = max(picked.values()) + 1
    return noms


def _kind(objet):
    o = fold(objet)
    if "amendement" in o:
        return "amendement"
    if "motion" in o:
        return "motion"
    if "ensemble" in o:
        return "ensemble"
    if re.search(r"\barticle", o):
        return "article"
    if "resolution" in o:
        return "résolution"
    return "autre"


def parse_votes(txt):
    """Votes nominatifs d'un compte rendu intégral (texte pdftotext en ordre de lecture).

    La mise en page en deux colonnes peut déplacer les listes de noms : les décomptes qui suivent
    l'annonce du vote font foi, et une liste n'est rattachée à un vote que si son type (oui, non,
    abstention) et son effectif correspondent exactement à ces décomptes.
    """
    flow = _flow(txt)
    marks = list(VOTE_MARK.finditer(flow))
    # les colonnes peuvent éloigner un décompte de son annonce ; chaque vote ayant un seul décompte,
    # on les apparie dans l'ordre quand leurs nombres concordent
    decomptes = list(DECOMPTE.finditer(flow))
    apparies = len(decomptes) == len(marks)
    lists = _lists(flow)
    state = {"ptr": 0}
    votes, prev_end, prev_docs = [], 0, []
    for k, m in enumerate(marks):
        region = flow[prev_end:m.start()]
        starts = [o.start() for o in OBJET.finditer(region)]
        if starts:
            objet = region[starts[-1]:]
        else:
            p = max(region.rfind("M. le Président. –"), region.rfind("Mme la Présidente. –"))
            objet = region[p:] if p >= 0 else region[-300:]
        objet = re.sub(r"^(M\. le Président|Mme la Présidente)\. –\s*", "", objet).strip()
        if len(objet) < 60:  # « Nous allons voter. » : on garde le contexte qui précède
            ctx = region[:starts[-1]] if starts else region
            p = max(ctx.rfind("M. le Président. –"), ctx.rfind("Mme la Présidente. –"))
            objet = (ctx[p:] if p >= 0 else ctx[-400:]).strip()[-500:] + " " + objet
            objet = re.sub(r"^(M\. le Président|Mme la Présidente)\. –\s*", "", objet).strip()
        objet = objet[:700]
        prev_end = m.end()

        c = decomptes[k] if apparies else m
        tot = {x: int(c.group(x)) if c.group(x) else 0 for x in ("oui", "non", "abst")}
        votants = int(c.group("tot")) if c.group("tot") else sum(tot.values())
        noms = _match_lists(lists, tot, state)

        # phrase de résultat : juste après les décomptes, sinon avant le vote suivant (après les listes)
        res_txt = m.group("res")
        if not res_txt:
            after = flow[m.end():marks[k + 1].start() if k + 1 < len(marks) else m.end() + 8000]
            mr = re.search(r"En conséquence,(.{0,250}?)\.", after)
            res_txt = mr.group(1) if mr else ""
        res_txt = fold(res_txt)
        attendu = "adopté" if tot["oui"] > tot["non"] else "rejeté"
        if "n'est pas adopt" in res_txt or "rejet" in res_txt:
            lu = "rejeté"
        elif "adopt" in res_txt:
            lu = "adopté"
        else:
            lu = None
        # une phrase incohérente avec les décomptes vient sans doute d'un autre vote (colonnes mêlées)
        if lu and (lu == attendu or not (tot["oui"] or tot["non"])):
            resultat, deduit = lu, False
        else:
            resultat, deduit = attendu, True

        docs = list(dict.fromkeys(f"{n}-{a}-{b}" for n, a, b in DOCREF.findall(objet)))
        if not docs and "meme" in fold(objet):
            docs = prev_docs
        prev_docs = docs or prev_docs
        votes.append({
            "objet": objet,
            "nature": _kind(objet[:160]),
            "docs": docs,
            "resultat": resultat,
            "resultat_deduit": deduit,
            "votants": votants,
            "pour": tot["oui"], "contre": tot["non"], "abstention": tot["abst"],
            "noms": noms,
        })
    return votes


def _pdftotext(raw):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext introuvable (paquet poppler-utils)")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "doc.pdf")
        with open(p, "wb") as f:
            f.write(raw)
        subprocess.run(["pdftotext", p, p + ".txt"], check=True, timeout=180)
        with open(p + ".txt", encoding="utf-8", errors="replace") as f:
            return f.read()


# à incrémenter quand parse_votes change : les comptes rendus déjà lus sont alors relus
ANALYSEUR_VOTES = 4


def votes():
    """Votes nominatifs des séances plénières de la législature (cache par compte rendu)."""
    cache_file = cache_path("wal_cri_votes.json")
    cache = read_json(cache_file, {})
    if cache.get("_version") != ANALYSEUR_VOTES:
        cache = {"_version": ANALYSEUR_VOTES}
    pubs = fetch_json(f"{OD}/publications_od.php?f=json&idleg={LEG}&type=CRI", timeout=300)["publications"]
    pubs = [p for p in pubs if p["PUB_TYPE"] == "CRI"]
    out = []
    for p in sorted(pubs, key=lambda p: date_fr(p["PUB_DATUM"]) or ""):
        key = p["PUB_ID"]
        if key not in cache:
            try:
                txt = _pdftotext(fetch(p["PUB_LIEN"].replace("http://", "https://"), binary=True, timeout=300))
                cache[key] = parse_votes(txt)
                log(f"wallonie: {p['PUB_REFERENCE']} → {len(cache[key])} votes")
            except Exception as e:  # un PDF illisible ne bloque pas la mise à jour
                log(f"wallonie: {p['PUB_REFERENCE']} ignoré ({e})")
                continue
            write_json(cache_file, cache)
        for i, v in enumerate(cache[key]):
            out.append(dict(v, id=f"wal-v-{key}-{i + 1}", parl="wal", date=date_fr(p["PUB_DATUM"]),
                            seance=p["PUB_REFERENCE"], url=p["PUB_LIEN"].replace("http://", "https://")))
    return out


# ---------------------------------------------------------------- autres publications récentes

def publications_recentes(types=("PARCHEMIN", "MOTION", "RES", "RAPPORT", "BT", "QR"), limite=300):
    pubs = fetch_json(f"{OD}/publications_od.php?f=json&idleg={LEG}", timeout=300)["publications"]
    pubs = [p for p in pubs if p["PUB_TYPE"] in types]
    pubs.sort(key=lambda p: date_fr(p["PUB_DATUM"]) or "", reverse=True)
    return [{
        "id": f"wal-pub-{p['PUB_ID']}", "parl": "wal", "type": clean(p["PUB_TYPECOMPLET"]),
        "ref": p["PUB_REFERENCE"], "date": date_fr(p["PUB_DATUM"]), "titre": clean(p["PUB_TITRE"]),
        "url": p["PUB_LIEN"].replace("http://", "https://"),
    } for p in pubs[:limite]]
