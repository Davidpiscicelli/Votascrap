"""Test du module de résumés IA avec un faux client (aucun appel réseau, aucune clé nécessaire)."""

import json
import os
import sys
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "collect"))

try:
    import anthropic  # noqa: F401
    HAS_SDK = True
except ImportError:
    HAS_SDK = False

import summarize  # noqa: E402

DOSSIER = {"id": "wal-657-2025-2026", "parl": "wal", "type": "Projet de décret", "num": "657 (2025-2026)",
           "titre": "Clusters d'innovation stratégique", "auteurs": "DOLIMONT Adrien", "statut": "adopté",
           "etapes": [{"date": "2026-07-17", "libelle": "Projet de décret"}, {"date": "2026-09-30", "libelle": "Texte adopté en séance plénière"}]}


class FakeMessages:
    def __init__(self, payload, stop="end_turn"):
        self.payload, self.stop, self.calls = payload, stop, []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.payload)])


class Resumes(unittest.TestCase):
    def test_message_contient_les_elements_du_dossier(self):
        msg = summarize.message_dossier(DOSSIER, "Exposé des motifs : ...")
        self.assertIn("Clusters d'innovation stratégique", msg)
        self.assertIn("2026-09-30 : Texte adopté en séance plénière", msg)
        self.assertIn("<document>", msg)

    def test_empreinte_change_quand_le_dossier_avance(self):
        a = summarize.empreinte(DOSSIER)
        b = summarize.empreinte(dict(DOSSIER, etapes=DOSSIER["etapes"] + [{"date": "2026-10-01", "libelle": "Sanction"}]))
        self.assertNotEqual(a, b)

    @unittest.skipUnless(HAS_SDK, "SDK anthropic absent")
    def test_appel_structure(self):
        rep = {"en_bref": "x", "resume": "y", "enjeux_entreprises": "z", "points_attention": [], "public_concerne": []}
        fake = FakeMessages(json.dumps(rep))
        cl = SimpleNamespace(beta=SimpleNamespace(messages=fake))
        out = summarize.ask(cl, "consigne", "message", schema=summarize.SCHEMA_DOSSIER)
        self.assertEqual(out, rep)
        kw = fake.calls[0]
        self.assertEqual(kw["fallbacks"], "default")
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")

    @unittest.skipUnless(HAS_SDK, "SDK anthropic absent")
    def test_refus_ou_troncature_ignores(self):
        for stop in ("refusal", "max_tokens"):
            cl = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages("{}", stop=stop)))
            self.assertIsNone(summarize.ask(cl, "c", "m", schema=summarize.SCHEMA_DOSSIER))


if __name__ == "__main__":
    unittest.main()
