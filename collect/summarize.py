"""Résumés « en langage clair » des dossiers et synthèses mensuelles, via l'API Claude (optionnel).

    ANTHROPIC_API_KEY=... python3 collect/summarize.py

Sans clé, le script ne fait rien : le site fonctionne sans résumés. Les consignes envoyées au modèle
sont dans prompts/ et sont publiées telles quelles sur la page « Transparence IA » du site.
"""

import hashlib
import json
import os
import sys

from common import SITE, ROOT, data_path, fetch, log, now_iso, read_json, write_json

IA = SITE["ia"]
PROMPTS = os.path.join(ROOT, "prompts")
EXTRAIT_MAX = 15000  # caractères du document déposé transmis au modèle (exposé des motifs, début du dispositif)

SCHEMA_DOSSIER = {
    "type": "object",
    "properties": {
        "en_bref": {"type": "string"},
        "resume": {"type": "string"},
        "enjeux_entreprises": {"type": "string"},
        "points_attention": {"type": "array", "items": {"type": "string"}},
        "public_concerne": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["en_bref", "resume", "enjeux_entreprises", "points_attention", "public_concerne"],
    "additionalProperties": False,
}


def prompt(name):
    with open(os.path.join(PROMPTS, name), encoding="utf-8") as f:
        return f.read().strip()


def client():
    import anthropic
    return anthropic.Anthropic()


def ask(cl, system, user, schema=None, max_tokens=4000):
    """Un appel Messages API ; renvoie le texte (ou le JSON décodé si un schéma est donné)."""
    import anthropic
    output_config = {"effort": IA.get("effort", "medium")}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    try:
        r = cl.beta.messages.create(
            model=IA["modele"],
            max_tokens=max_tokens,
            # en cas de refus d'un classifieur de sécurité, l'API relance la requête sur le modèle recommandé
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config=output_config,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.RateLimitError:
        raise
    except anthropic.APIStatusError as e:
        log(f"ia: erreur API {e.status_code} : {e.message}")
        return None
    if r.stop_reason == "refusal":
        log("ia: requête déclinée par le modèle")
        return None
    if r.stop_reason == "max_tokens":
        log("ia: réponse tronquée (max_tokens)")
        return None
    text = next((b.text for b in r.content if b.type == "text"), "")
    return json.loads(text) if schema else text.strip()


def extrait_pdf(url):
    if not url:
        return ""
    from wallonie import _pdftotext  # pdftotext (poppler-utils)
    try:
        txt = _pdftotext(fetch(url.split("#")[0], binary=True, timeout=180))
    except Exception as e:  # noqa: BLE001
        log(f"ia: PDF illisible {url} ({e})")
        return ""
    txt = " ".join(txt.split())
    return txt[:EXTRAIT_MAX]


def empreinte(d):
    """Change quand le dossier avance : le résumé est alors refait."""
    return hashlib.sha1(json.dumps([d["titre"], d["statut"], len(d.get("etapes", []))]).encode()).hexdigest()[:12]


def message_dossier(d, extrait):
    parl = {"wal": "Parlement de Wallonie", "bxl": "Parlement bruxellois / COCOM"}.get(d["parl"], d["parl"])
    etapes = "\n".join(f"- {e['date']} : {e['libelle']}" for e in d.get("etapes", [])[:40])
    return (f"Assemblée : {parl}\nType : {d['type']}\nNuméro : {d.get('num', '')}\n"
            f"Intitulé : {d['titre']}\nAuteurs : {d.get('auteurs') or 'non précisé'}\n"
            f"Statut actuel : {d['statut']}\n\nÉtapes de la procédure :\n{etapes or '- (aucune étape publiée)'}\n\n"
            f"Extrait du document déposé ({'premiers ' + str(len(extrait)) + ' caractères' if extrait else 'indisponible'}) :\n"
            f"<document>\n{extrait}\n</document>")


def resumer_dossiers(cl, limite):
    dossiers = read_json(data_path("dossiers.json"), [])
    resumes = read_json(data_path("resumes.json"), {})
    todo = [d for d in dossiers if resumes.get(d["id"], {}).get("empreinte") != empreinte(d)]
    # priorité : radar PME d'abord, puis dossiers les plus récemment actifs (tri stable)
    todo.sort(key=lambda d: d.get("date_maj") or "", reverse=True)
    todo.sort(key=lambda d: not d.get("radar"))
    system = prompt("resume_dossier.md")
    fait = 0
    for d in todo[:limite]:
        res = ask(cl, system, message_dossier(d, extrait_pdf(d.get("pdf"))), schema=SCHEMA_DOSSIER)
        if res:
            resumes[d["id"]] = dict(res, empreinte=empreinte(d), modele=IA["modele"], genere_le=now_iso())
            fait += 1
            write_json(data_path("resumes.json"), resumes)
    log(f"ia: {fait} résumés de dossiers (reste {max(0, len(todo) - limite)})")


def syntheses_mensuelles(cl):
    syn = read_json(data_path("syntheses.json"), [])
    dossiers = {d["id"]: d for d in read_json(data_path("dossiers.json"), [])}
    store = read_json(data_path("syntheses_ia.json"), {})
    system = prompt("synthese_mensuelle.md")
    for i, s in enumerate(syn):
        courant = i == 0  # le mois en cours est réécrit à chaque exécution
        if s["mois"] in store and not courant:
            continue
        faits = {
            "mois": s["libelle"],
            "questions_par_assemblee": s["questions"],
            "questions_radar_pme": s["questions_radar"],
            "themes_des_questions": s["themes"],
            "votes_nominatifs_wallonie": s["votes"],
            "dossiers_adoptes": [dossiers[x]["titre"] for x in s["dossiers_adoptes"] if x in dossiers][:15],
            "dossiers_deposes": [dossiers[x]["titre"] for x in s["dossiers_deposes"] if x in dossiers][:20],
            "dossiers_radar": [dossiers[x]["titre"] for x in s["dossiers_deposes"] + s["dossiers_adoptes"]
                               if x in dossiers and dossiers[x].get("radar")][:10],
        }
        txt = ask(cl, system, json.dumps(faits, ensure_ascii=False, indent=1), max_tokens=3000)
        if txt:
            store[s["mois"]] = txt
            s["texte_ia"] = txt
    write_json(data_path("syntheses_ia.json"), store)
    write_json(data_path("syntheses.json"), syn)


def main():
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")) and "--forcer" not in sys.argv:
        log("ia: pas de clé ANTHROPIC_API_KEY — résumés ignorés (le site fonctionne sans)")
        return 0
    cl = client()
    resumer_dossiers(cl, int(IA.get("max_resumes_par_execution", 40)))
    syntheses_mensuelles(cl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
