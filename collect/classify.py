"""Étiquetage thématique par mots-clés (config/themes.json) et par matières officielles wallonnes."""

import re

from common import fold, load_config


def _compile(keywords):
    parts = []
    for kw in keywords:
        k = fold(kw)
        prefix = k.endswith("*")
        k = re.escape(k.rstrip("*")).replace(r"\*", r"\w*")
        parts.append(r"(?<![\w-])" + k + (r"[\w-]*" if prefix else r"(?![\w-])"))
    return re.compile("|".join(parts)) if parts else None


class Classifier:
    def __init__(self, cfg=None, matieres=None):
        cfg = cfg or load_config("themes.json")
        # matieres : {mat_id: rubrique} issu du thésaurus du Parlement de Wallonie
        matieres = matieres or {}
        self.themes = []
        for t in cfg["themes"]:
            mats = {str(m) for m in t.get("wal_mat", [])}
            cats = {fold(c) for c in t.get("wal_cat", [])}
            mats |= {mid for mid, cat in matieres.items() if fold(cat) in cats}
            self.themes.append((t["id"], _compile(t.get("keywords", [])), mats))
        r = cfg["radar"]
        self.radar_re = _compile(r.get("keywords", []))
        self.radar_mats = {str(m) for m in r.get("wal_mat", [])}
        self.labels = {t["id"]: t["label"] for t in cfg["themes"]}

    def tag(self, *texts, mat=None):
        """Renvoie (liste des thèmes, booléen radar)."""
        txt = fold(" ".join(t for t in texts if t))
        mat = str(mat) if mat not in (None, "") else None
        found = []
        for tid, rx, mats in self.themes:
            if (mat and mat in mats) or (rx and rx.search(txt)):
                found.append(tid)
        radar = bool((mat and mat in self.radar_mats) or (self.radar_re and self.radar_re.search(txt)))
        return found, radar
