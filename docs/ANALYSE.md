# Analyse : Votalis, sources parlementaires et choix de Plénière

*Analyse réalisée le 9 octobre 2026.*

## 1. Votalis : ce qu'on peut en savoir

votalis.be est protégé par un contrôle anti-robots Cloudflare (réponse 403, page « Just a moment… »). Le code et les pages internes n'ont donc pas été consultés, et ce contrôle n'a pas été contourné. Les informations ci-dessous viennent de la page d'accueil telle qu'elle est indexée par les moteurs de recherche.

**Positionnement.** « Le parlement, en langage clair » : un projet citoyen, en bêta, qui résume, indexe et rend accessibles les questions, débats et votes des parlements belges.

**Périmètre annoncé.** Wallonie, Bruxelles, Flandre et fédéral (« chaque séance lue, résumée et indexée »), plus des documents officiels de la Communauté germanophone.

**Volumes affichés.** 15 512 votes reliés à leurs textes et 57 636 questions aux ministres.

**Fonctions annoncées.**
- Base de dossiers : chaque dossier regroupe ses votes, ses débats et ses questions.
- Élus et partis : qui parle, qui vote, qui s'abstient ; lignes de parti et votes dissidents.
- Synthèses mensuelles.
- Assistant qui répond aux questions à partir des comptes rendus, en citant ses sources.
- Comptes utilisateurs (pas encore ouverts) : suivre ses élus et recevoir une alerte à chaque vote.
- Une page « Transparence IA » en pied de page, qui publierait les consignes données au modèle. Elle n'a pas pu être lue à cause de la protection anti-robots. Si son contenu est collé ici, il pourra servir à comparer les méthodes. Ses textes ne seront pas recopiés : les consignes de Plénière sont rédigées séparément (`prompts/`).

## 2. Correspondance des fonctions

| Fonction Votalis | Plénière (v1) | Commentaire |
|---|---|---|
| Dossiers avec votes, débats, questions | **Oui** (Wallonie, Bruxelles) | Chronologie officielle complète, votes wallons reliés au dossier par le numéro de document |
| Résumés en langage clair | **Oui** (dossiers) | Via l'API Claude, consignes publiées, au plus 40 par jour |
| Votes nominatifs, lignes de parti, dissidences | **Oui** (Wallonie) | Lus dans les comptes rendus PDF, contrôlés contre les décomptes officiels |
| Questions aux ministres | **Oui** (Wallonie, Bruxelles) | Environ 27 500 questions pour la législature en cours |
| Élus et partis | **Oui** (Wallonie) | Questions, votes, votes contre la ligne, cohésion des groupes |
| Synthèses mensuelles | **Oui** | Chiffres calculés, texte rédigé par IA si la clé est configurée |
| Transparence IA | **Oui** | Consignes intégrales sur la page Méthode, modèle et extrait transmis expliqués |
| Suivre des élus, alertes | **Partiel** | « Suivre » mémorisé dans le navigateur + flux Atom du radar ; pas de comptes ni d'e-mails |
| Résumé de chaque séance (débats) | **Non** (phase 2) | Faisable à partir des CRI/CRIC, coût IA plus élevé |
| Assistant questions-réponses | **Non** (phase 2) | Nécessite un petit serveur (fonction Netlify + API Claude) |
| Fédéral, Flandre, germanophones | **Non** | Sites protégés contre les accès automatisés (voir §4) |
| Radar PME & indépendants | **En plus** | Spécifique à l'angle UCM, réglable dans `config/themes.json` |

## 3. Sources utilisées

### Parlement de Wallonie (couverture complète)

| Donnée | Accès | Format | Remarques |
|---|---|---|---|
| Députés | `opendata/composition_dep_od.php?f=json` | JSON | 75 députés, parti, circonscription, photo |
| Publications | `opendata/publications_od.php?f=json&idleg=12` | JSON | 3 582 publications pour 2024-2029 (décrets, CRI, CRIC, motions, résolutions…). Le filtre `idses` est ignoré par le serveur |
| Thésaurus des matières | `ajax?p=matieres` | HTML | 363 matières en 21 rubriques, dont « P.M.E./T.P.E./Indépendants » (97), « Aides aux entreprises » (74), « Simplification administrative » (264) |
| Questions et interpellations | `pwpages?p=interp-questions-recherche&idleg=12&type=…` | HTML | Une page par type : 11 260 questions écrites, 8 101 orales, 598 d'actualité, 183 urgentes, 126 interpellations. Matière officielle pour les questions écrites |
| Dossiers législatifs | `pwpages?p=doc-recherche&idleg=12&type=alldecbud` (+ `type=94` pour les résolutions) puis `doc-recherche-det&iddoc=…` | HTML | Chronologie codée par type d'étape (dépôt, exposé, discussion, vote en commission, rapport, texte adopté, parchemin) |
| Votes nominatifs | Comptes rendus intégraux (CRI) en PDF | PDF → texte | Bloc « Il est procédé au vote nominatif », décomptes, listes « Ont répondu oui / non / Se sont abstenus » |
| Flux | `actu/rss_doc_generator.php?aff=rss&type=…` | RSS | Non utilisés : l'open data est plus complet |

Licence : décret conjoint du 12 juillet 2017 (réutilisation des informations du secteur public). Il faut citer la source et la date de mise à jour.

### Parlement bruxellois et COCOM

| Donnée | Accès | Format | Remarques |
|---|---|---|---|
| Questions | `prb_includes/weblex/data/dos_qu_legis_24-29.json` | JSON | 7 439 questions et interpellations (PRB + ARCCC) |
| Dossiers législatifs | `prb_includes/weblex/data/dos_leg_legis_24-29.json` | JSON | 340 dossiers |
| Fiche de dossier | `weblex-doc-det/?moncode=…` | HTML | Auteurs, date de vote, de promulgation, de publication, historique complet |
| Flux | `prb_includes/prb-DOC-fr.rss`, etc. | RSS | 10 derniers éléments seulement |

Le fichier `robots.txt` n'exclut que le robot d'OpenAI ; la veille s'identifie et espace ses requêtes.

### Parlement de la Fédération Wallonie-Bruxelles

Le site (Nuxt + Drupal) ne publie pas de jeu de données ouvert. La recherche de documents passe par un service tiers (Algolia), qui n'est pas utilisé ici. Le sitemap est inexploitable : il contient des milliers d'entrées en double. La veille lit l'état initial de la page « Documents parlementaires » (18 derniers documents) et accumule les résultats d'un jour à l'autre. **Limite** : les jours très chargés, une partie des documents peut manquer.

### Non accessibles depuis un robot

| Assemblée | Constat |
|---|---|
| Chambre (lachambre.be) | Pare-feu applicatif : « Request Rejected ». Le portail `data.dekamer.be` est une version d'essai de 2016 |
| Parlement flamand | 403 (protection anti-robots) ; l'API `ws.vlaamsparlement.be` ne répondait pas depuis l'environnement de test |
| Communauté germanophone (pdg.be) | 403 |

## 4. Pistes pour la phase 2

1. **Fédéral** : demander à la Chambre un accès à ses données (le service informatique annonce une API REST) ; à défaut, recevoir les bulletins de questions et réponses (QRVA) par abonnement et les traiter. C'est le niveau du statut social des indépendants : la piste la plus utile pour UCM.
2. **Flandre** : tester l'API `ws.vlaamsparlement.be` depuis GitHub Actions ; elle est documentée et ouverte.
3. **Votes bruxellois** : les CRI bruxellois contiennent aussi des votes nominatifs ; le même analyseur peut être adapté.
4. **Résumés de séances** : résumer chaque compte rendu de commission (CRIC) des commissions Économie-Emploi-Formation (Wallonie) et Économie-Emploi (Bruxelles).
5. **Assistant questions-réponses** : index des comptes rendus + fonction serveur appelant l'API Claude, avec citations.
6. **Alertes e-mail** : envoi hebdomadaire du radar depuis le workflow (Brevo ou SMTP), par thème.

## 5. Limites et risques

- **Mise en page des PDF** : sur deux colonnes, les listes de noms peuvent être coupées. Une liste n'est rattachée à un vote que si son effectif égale le décompte officiel. Sur les comptes rendus testés, 35 votes sur 37 avaient leur détail nominatif ; les autres n'affichent que les décomptes.
- **Évolution des sites** : un changement de mise en page casse un collecteur. Les tests sur extraits réels et l'état des sources sur la page Méthode servent d'alerte.
- **Résumés IA** : ils reposent sur un extrait du document déposé et peuvent manquer un amendement. Ils sont signalés comme tels et renvoient au texte officiel.
- **Classement par mots-clés** : simple et transparent, mais imparfait (faux positifs et oublis). Les listes s'affinent dans `config/themes.json`.
