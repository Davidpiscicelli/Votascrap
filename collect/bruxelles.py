"""Parlement de la Région de Bruxelles-Capitale (PRB) et Assemblée réunie de la COCOM (ARCCC).

Sources publiques :
- Jeux de données JSON qui alimentent les tableaux du site (questions, dossiers législatifs)
- Fiches dossiers « weblex » (historique, auteurs, dates de vote et de publication)
"""

import html
import re

from common import clean, date_fr, fetch, fetch_json, fold, log, SITE

BASE = "https://www.parlement.brussels"
LEG = SITE["bruxelles"]["legislature"]
ASSEMBLEES = {"PRB": "Parlement bruxellois", "ARCCC": "Assemblée réunie (COCOM)"}


def _href(cell):
    m = re.search(r'href="([^"]+)"', cell or "")
    if not m:
        return None
    u = clean(m.group(1)).replace("&montitre=", "")
    return u if u.startswith("http") else BASE + u


def questions():
    rows = fetch_json(f"{BASE}/prb_includes/weblex/data/dos_qu_legis_{LEG}.json", timeout=300)["data"]
    out = []
    for r in rows:
        url = _href(r[2])
        code = re.search(r"moncode=(\d+)", url or "")
        dest = clean(r[11])
        ministre, _, fonction = dest.partition(" - ")
        titre = clean(r[8])
        titre = re.sub(r"^(Question (écrite|orale|d'actualité)|Interpellation|Demande d'explications?)\s+"
                       r"(concernant|relative?s? à|sur)\s+", "", titre, flags=re.I)
        out.append({
            "id": f"bxl-q-{code.group(1) if code else len(out)}",
            "parl": "bxl",
            "assemblee": r[0],
            "type": clean(r[6]).capitalize(),
            "date": date_fr(r[5]),
            "auteur": clean(r[10]),
            "destinataire": ministre.strip(),
            "fonction": fonction.strip(),
            "titre": titre[:1].upper() + titre[1:] if titre else "",
            "publie": bool(clean(r[13])),
            "url": url,
        })
    log(f"bruxelles: {len(out)} questions")
    return out


ROW = re.compile(r"<tr>\s*<td[^>]*>\s*([\d/]{10})\s*</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>"
                 r"\s*<td[^>]*>(.*?)</td>", re.S)


def parse_fiche(h):
    sec = h[h.find('id="weblex-doc-det-fr"'):]
    sec = html.unescape(sec[:sec.find("</section>")])
    info = {}
    for lab, key in (("Auteur", "auteurs"), ("Date de vote", "date_vote"),
                     ("Date de promulgation", "date_promulgation"), ("Date de publication", "date_publication")):
        m = re.search(rf"<b>{lab}:\s*</b>\s*(?:</td>\s*<td[^>]*>)?(.*?)</td>", sec, re.S)
        if m:
            v = clean(m.group(1).replace("<br>", ", "))
            info[key] = date_fr(v) if key.startswith("date") else v
    etapes = []
    for d, lib, aut, ref in ROW.findall(sec):
        etapes.append({"date": date_fr(d), "libelle": clean(lib), "auteurs": clean(aut),
                       "doc": clean(ref) or None, "url": _href(ref.replace("'", '"'))})
    info["etapes"] = etapes
    return info


def statut(info):
    libs = " | ".join(fold(e["libelle"]) for e in info.get("etapes", []))
    if "rejet" in libs:
        return "rejeté"
    if info.get("date_vote") or info.get("date_promulgation") or re.search(r"adopte\(e\) en seance|adoption en seance", libs):
        return "adopté"
    if "caduc" in libs or "retir" in libs:
        return "retiré"
    if "adopte(e) en commission" in libs or "rapport" in libs:
        return "rapport de commission"
    if "commission" in libs:
        return "en commission"
    return "déposé"


def dossiers(previous, max_fiches=120):
    rows = fetch_json(f"{BASE}/prb_includes/weblex/data/dos_leg_legis_{LEG}.json", timeout=300)["data"]
    out, fetched = [], 0
    # fiches à (re)lire en priorité : nouvelles, puis non clôturées, des plus récentes aux plus anciennes
    rows = sorted(rows, key=lambda r: date_fr(r[5]) or "", reverse=True)
    for r in rows:
        url = _href(r[2])
        m = re.search(r"moncode=([A-Z0-9]+)", url or "")
        did = f"bxl-{r[0]}-{m.group(1) if m else len(out)}"
        cell = r[8]
        ref = clean(re.search(r">([^<]+)</a>", cell).group(1)) if "</a>" in cell else ""
        titre = clean(re.sub(r"^.*?</a>\s*-\s*", "", cell))
        old = previous.get(did, {})
        info = {k: old[k] for k in ("auteurs", "date_vote", "date_promulgation", "date_publication", "etapes") if k in old}
        final = old.get("statut") in ("adopté", "rejeté", "retiré")
        if url and (not old or not final) and fetched < max_fiches:
            try:
                info = parse_fiche(fetch(url))
                fetched += 1
            except RuntimeError as e:
                log(f"bruxelles: fiche {did} ignorée ({e})")
        etapes = info.get("etapes", [])
        dates = [e["date"] for e in etapes if e["date"]] or [date_fr(r[5])]
        commission = next((re.sub(r"^Renvoi (en )?", "", e["libelle"]) for e in etapes
                           if fold(e["libelle"]).startswith("renvoi commission")), None)
        out.append({
            "id": did,
            "parl": "bxl",
            "assemblee": r[0],
            "num": ref,
            "type": clean(r[6]),
            "titre": titre,
            "auteurs": info.get("auteurs", ""),
            "date_depot": date_fr(r[5]),
            "date_maj": max(d for d in dates if d),
            "statut": statut(info) if etapes else old.get("statut", "déposé"),
            "date_vote": info.get("date_vote"),
            "date_publication": info.get("date_publication"),
            "commission": commission,
            "etapes": etapes,
            "url": url,
            "pdf": _href(cell),
        })
    log(f"bruxelles: {len(out)} dossiers ({fetched} fiches lues)")
    return out
