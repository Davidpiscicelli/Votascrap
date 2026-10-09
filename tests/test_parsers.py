"""Tests des analyseurs sur des extraits réels des sites parlementaires (aucun accès réseau).

    python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "collect"))

import bruxelles  # noqa: E402
import wallonie  # noqa: E402
from classify import Classifier  # noqa: E402


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return f.read()


class VotesWallonie(unittest.TestCase):
    def test_trois_votes_successifs(self):
        votes = wallonie.parse_votes(fixture("cri_extrait.txt"))
        self.assertEqual([v["nature"] for v in votes], ["amendement", "article", "ensemble"])
        self.assertEqual([(v["pour"], v["contre"], v["abstention"]) for v in votes], [(71, 0, 0), (65, 0, 6), (71, 0, 0)])
        for v in votes:
            # les listes nominatives correspondent exactement aux décomptes officiels
            self.assertEqual(len(v["noms"]["oui"]), v["pour"])
            self.assertEqual(len(v["noms"]["abst"]), v["abstention"])
            self.assertEqual(v["docs"], ["601-2025-2026"])

    def test_vote_divise(self):
        (v,) = wallonie.parse_votes(fixture("cri_extrait_divise.txt"))
        self.assertEqual((v["pour"], v["contre"], v["abstention"]), (40, 31, 0))
        self.assertEqual(v["resultat"], "adopté")
        self.assertFalse(v["resultat_deduit"])
        self.assertEqual(v["nature"], "motion")
        self.assertEqual(v["docs"], ["619-2025-2026"])
        self.assertIn({"nom": "Rachida Aït Alouha", "parti": "Indépendante"}, v["noms"]["non"])
        noms = [n["nom"] for k in v["noms"] for n in v["noms"][k]]
        self.assertEqual(len(noms), len(set(noms)))

    def test_liste_incomplete_non_rattachee(self):
        # un décompte qui ne correspond à aucune liste ne doit pas recevoir de noms
        txt = fixture("cri_extrait_divise.txt").replace("40 membres répondent oui.", "41 membres répondent oui.")
        (v,) = wallonie.parse_votes(txt)
        self.assertEqual(v["noms"], {"oui": [], "non": [], "abst": []})


class QuestionsEtDossiersWallonie(unittest.TestCase):
    def test_questions(self):
        qs = wallonie.parse_questions(fixture("wal_questions.html"), "Question écrite")
        self.assertEqual(len(qs), 3)
        q = qs[0]
        self.assertEqual(q["auteur"], "Anne-Catherine Goffinet")
        self.assertEqual(q["destinataire"], "Anne-Catherine Dalcq")
        self.assertTrue(q["titre"][0].isupper())
        self.assertTrue(q["fonction"].startswith("Ministre"))
        self.assertEqual(q["date"], "2026-10-09")
        self.assertEqual(q["num"], "100 (2026-2027)")
        self.assertEqual(q["mat"], "155")

    def test_dossier_chronologie_et_statut(self):
        etapes = wallonie.parse_dossier_detail(fixture("wal_dossier_657.html"))
        self.assertEqual(len(etapes), 14)
        self.assertEqual(etapes[0]["libelle"], "Projet de décret")
        self.assertEqual(etapes[0]["doc"], "DECRET 657 N° 1 (2025-2026)")
        self.assertTrue(etapes[0]["url"].startswith("https://"))
        self.assertEqual(wallonie.statut_dossier(etapes), "adopté")
        self.assertEqual(wallonie.statut_dossier(etapes[:5]), "en commission")
        self.assertEqual(wallonie.statut_dossier(etapes[:1]), "déposé")


class Noms(unittest.TestCase):
    def test_nom_lisible(self):
        from common import nom_lisible, noms_lisibles
        self.assertEqual(nom_lisible("GOFFINET Anne-Catherine"), "Anne-Catherine Goffinet")
        self.assertEqual(nom_lisible("CASSART-MAILLEUX Caroline"), "Caroline Cassart-Mailleux")
        self.assertEqual(nom_lisible("de WASSEIGE Olivier"), "Olivier de Wasseige")
        self.assertEqual(nom_lisible("Nawal Ben Hamou"), "Nawal Ben Hamou")
        self.assertEqual(noms_lisibles("DOLIMONT Adrien, JEHOLET Pierre-Yves"), "Adrien Dolimont, Pierre-Yves Jeholet")


class Bruxelles(unittest.TestCase):
    def test_fiche(self):
        info = bruxelles.parse_fiche(fixture("bxl_fiche_A10.html"))
        self.assertEqual(info["date_vote"], "2024-10-04")
        self.assertEqual(info["date_publication"], "2024-10-22")
        self.assertIn("Weytsman David", info["auteurs"])
        self.assertEqual(info["etapes"][0]["libelle"], "Dépôt")
        self.assertEqual(bruxelles.statut(info), "adopté")


class Classement(unittest.TestCase):
    def setUp(self):
        self.clf = Classifier(matieres={"97": "Expansion économique", "131": "Politique de l’emploi"})

    def test_mots_cles_et_radar(self):
        themes, radar = self.clf.tag("Le soutien aux PME et aux indépendants en difficulté")
        self.assertIn("pme", themes)
        self.assertTrue(radar)

    def test_accents_et_frontieres_de_mots(self):
        themes, _ = self.clf.tag("Les aides à l'emploi APE et le FOREm")
        self.assertIn("emploi", themes)
        # « ape » ne doit pas être reconnu à l'intérieur d'un autre mot
        _, radar = self.clf.tag("La papeterie wallonne")
        self.assertFalse(radar)

    def test_matiere_officielle(self):
        themes, radar = self.clf.tag("Question sans mot-clé", mat="97")
        self.assertIn("pme", themes)
        self.assertTrue(radar)


if __name__ == "__main__":
    unittest.main()
