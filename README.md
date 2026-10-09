# Plénière : veille parlementaire Wallonie · Bruxelles · FWB

Site de veille qui rassemble, classe et résume l'activité des parlements francophones : dossiers législatifs avec leur chronologie, questions aux ministres, votes nominatifs, activité des élus et synthèses mensuelles. Un **radar PME & indépendants** repère ce qui touche directement les entreprises, l'emploi et la formation.

Le fonctionnement s'inspire de Votalis (votalis.be), mais le projet est **reconstruit à partir des sources officielles**. Il ne contient ni le code, ni les textes, ni la marque de Votalis. L'analyse comparative et le détail des sources sont dans [docs/ANALYSE.md](docs/ANALYSE.md).

## Ce que fait le site

| Rubrique | Contenu |
|---|---|
| Accueil | Synthèse du mois, radar PME, textes adoptés récemment, derniers votes, thèmes des questions, derniers documents FWB |
| Dossiers | Décrets, ordonnances, résolutions, budgets : statut (déposé, en commission, rapport, adopté, rejeté), chronologie complète, documents, votes liés, résumé en langage clair |
| Questions | Questions écrites, orales, d'actualité, urgentes, interpellations et demandes d'explications ; filtres par parlement, type, ministre, thème, radar |
| Votes | Votes nominatifs en plénière wallonne : hémicycle, détail par groupe, votes contre la ligne du groupe |
| Élus | Les 75 députés wallons : questions posées, votes relevés, votes contre la ligne ; tableau de cohésion des groupes |
| Synthèses | Un bilan chiffré par mois, avec un texte rédigé par IA si la clé est configurée |
| Mes suivis | Dossiers et élus suivis, mémorisés dans le navigateur |
| Méthode | Sources, fraîcheur de chaque source, règles de classement, consignes complètes données à l'IA |

Un flux Atom du radar (`site/data/flux-radar.xml`) permet de recevoir les nouveautés dans Outlook ou un lecteur de flux.

## Couverture

- **Parlement de Wallonie** : couverture complète (open data officiel, moteur « Travail parlementaire », comptes rendus intégraux pour les votes).
- **Parlement bruxellois et Assemblée réunie de la COCOM** : questions et dossiers législatifs, avec chronologie, date de vote et de publication.
- **Parlement de la Fédération Wallonie-Bruxelles** : derniers documents publiés, accumulés d'une mise à jour à l'autre.
- **Non couverts** : Chambre, Parlement flamand, Parlement de la Communauté germanophone. Leurs sites bloquent les accès automatisés, et la veille ne contourne pas ces protections. Voir les pistes dans [docs/ANALYSE.md](docs/ANALYSE.md).

## Mettre à jour les données

### Automatiquement (recommandé)

Le workflow `.github/workflows/veille.yml` tourne chaque jour du lundi au samedi à 05 h 17 UTC. Il :

1. installe Python, Node et `pdftotext` ;
2. lance les tests des analyseurs ;
3. collecte les données (`collect/build.py`) ;
4. rédige les résumés IA si le secret `ANTHROPIC_API_KEY` existe (`collect/summarize.py`) ;
5. enregistre les données dans le dépôt, puis publie le site sur GitHub Pages.

Pour lancer une mise à jour à la demande : onglet **Actions** → **Mise à jour de la veille** → **Run workflow**.

Mise en place, une seule fois :

1. **Settings → Pages → Build and deployment → Source : GitHub Actions.** GitHub Pages est gratuit pour un dépôt public. Pour un dépôt privé, il faut un compte GitHub Pro, ou bien publier `site/` sur Netlify (voir plus bas).
2. *(Facultatif)* **Settings → Secrets and variables → Actions → New repository secret** : `ANTHROPIC_API_KEY` = votre clé API Anthropic. Sans elle, le site fonctionne sans résumés IA.
3. Renseigner l'adresse publique du site dans `config/site.json` (`url_publique`), pour que les liens du flux Atom pointent au bon endroit.

Le planning ne s'exécute que sur la branche par défaut du dépôt.

### À la main, sur un ordinateur

```bash
# prérequis : Python 3.10+, Node 18+, poppler-utils (pdftotext)
pip install -r requirements.txt
python3 collect/build.py               # collecte complète, environ 10 min la première fois puis 3 à 5 min
python3 collect/build.py --sans-votes  # plus rapide : ne relit pas les comptes rendus PDF
ANTHROPIC_API_KEY=sk-ant-... python3 collect/summarize.py   # facultatif
python3 -m http.server -d site 8000    # puis ouvrir http://localhost:8000
```

Chaque source est indépendante. Si l'une tombe en panne, les données précédentes sont conservées et la page **Méthode** affiche la source « En échec », avec l'erreur.

## Régler la veille

| Fichier | À quoi il sert |
|---|---|
| `config/themes.json` | Thèmes et **radar PME** : listes de mots-clés (accents ignorés, `*` en fin de mot = préfixe), matières officielles wallonnes associées |
| `config/site.json` | Nom du site, législatures suivies, types de questions, délai entre deux requêtes, modèle IA et plafond de résumés par exécution |
| `prompts/resume_dossier.md` | Consigne donnée à l'IA pour résumer un dossier (publiée telle quelle sur la page Méthode) |
| `prompts/synthese_mensuelle.md` | Consigne pour la synthèse du mois |

Après une modification de `themes.json`, relancez `build.py` : tout est reclassé.

**Changement de législature** (2029) : mettre à jour `wallonie.legislature_id` (identifiant donné par `opendata/legislatures_od.php?f=json`), `wallonie.legislature`, `wallonie.date_min_questions` et `bruxelles.legislature` dans `config/site.json`.

## IA : coût et garde-fous

- Modèle : `claude-opus-5-5` (modifiable dans `config/site.json`), effort `medium`.
- Au plus **40 résumés par exécution** ; un dossier n'est résumé à nouveau que s'il a avancé (nouvelle étape ou nouveau statut). Les dossiers du radar passent en premier.
- Le modèle reçoit l'intitulé, les étapes et les 15 000 premiers caractères du document déposé. La page Méthode le dit clairement, et chaque résumé renvoie au texte officiel.
- En cas de refus d'un filtre de sécurité, l'API relance la requête sur un modèle de repli (option `fallbacks: "default"`). Si le refus persiste, le dossier est simplement laissé sans résumé.
- Les résumés déjà produits sont conservés dans `site/data/resumes.json` ; ils ne sont pas refacturés.

## Publier ailleurs que sur GitHub Pages

Le site est entièrement statique : le dossier `site/` suffit. Sur **Netlify** : nouveau site depuis le dépôt, dossier de publication `site`, aucune commande de build (les données sont produites par le workflow GitHub et poussées dans le dépôt).

## Structure

```
collect/            collecteurs et traitements (Python, bibliothèque standard)
  common.py         HTTP poli (délai, nouvelles tentatives, User-Agent identifiable), normalisation
  wallonie.py       députés, thésaurus, questions, dossiers, votes nominatifs (PDF)
  bruxelles.py      questions et dossiers (PRB + COCOM)
  fwb.py            derniers documents FWB (+ nuxt_payload.js)
  classify.py       thèmes et radar par mots-clés et matières officielles
  build.py          orchestration, liens votes ↔ dossiers, statistiques, synthèses, flux Atom
  summarize.py      résumés et synthèses par l'API Claude (facultatif)
config/             réglages (thèmes, radar, législatures, IA)
prompts/            consignes IA (publiées sur le site)
site/               site statique (index.html, app.js, style.css) et data/ générées
cache/              votes déjà extraits des comptes rendus (évite de relire les PDF)
tests/              tests des analyseurs sur des extraits réels : python3 -m unittest discover -s tests
docs/ANALYSE.md     analyse de Votalis, des sources et des évolutions possibles
```

## Quand une source change

Les sites parlementaires changent parfois leur mise en page. Symptômes : la page Méthode montre une source « En échec », ou les tests échouent dans le workflow. Pour corriger :

1. Télécharger la page concernée et la comparer avec l'extrait de `tests/fixtures/`.
2. Adapter l'expression régulière du collecteur (`wallonie.py`, `bruxelles.py` ou `fwb.py`).
3. Remplacer la fixture par la nouvelle page et relancer les tests.

## Données et réutilisation

Les données du Parlement de Wallonie sont publiées sous le régime du décret du 12 juillet 2017 relatif à la réutilisation des informations du secteur public : il faut citer la source et la date de mise à jour (le pied de page et l'en-tête du site le font). Les débats parlementaires ne sont pas protégés par le droit d'auteur. Les autres parlements publient leurs documents librement ; la veille renvoie toujours au document officiel, qui fait foi.
