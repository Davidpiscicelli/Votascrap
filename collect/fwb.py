"""Parlement de la Fédération Wallonie-Bruxelles.

Le site public (Nuxt) n'expose pas de jeu de données ouvert : on lit l'état initial de la page
« Documents parlementaires » (les derniers documents publiés) et on accumule d'une exécution à l'autre.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from common import fetch, log

BASE = "https://www.pfwb.be"
HERE = os.path.dirname(os.path.abspath(__file__))


def _nuxt(html):
    if not shutil.which("node"):
        raise RuntimeError("node introuvable")
    p = subprocess.run(["node", os.path.join(HERE, "nuxt_payload.js")], input=html, capture_output=True,
                       text=True, timeout=60, check=True)
    return json.loads(p.stdout)


def documents_recents():
    state = _nuxt(fetch(f"{BASE}/documents-parlementaires"))
    docs = []
    for v in state.get("fetch", {}).values():
        if isinstance(v, dict) and isinstance(v.get("documents"), list):
            docs = v["documents"]
    out = []
    for d in docs:
        ts = d.get("date")
        out.append({
            "id": f"fwb-{d['nid']}",
            "parl": "fwb",
            "type": d.get("documentTypes") or "Document",
            "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else None,
            "titre": (d.get("description") or d.get("title") or "").strip(),
            "auteurs": ", ".join(d.get("authors") or []) if isinstance(d.get("authors"), list) else (d.get("authors") or ""),
            "groupes": d.get("politicalGroups") or [],
            "session": (d.get("sessions") or [None])[0],
            "url": BASE + d["url"] if d.get("url") else None,
        })
    log(f"fwb: {len(out)} documents récents")
    return out
