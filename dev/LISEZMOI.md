# Mycota — source, assemblage, essais

```
dev/
  src/app.html          toute l'app : styles, données du Mycodex, code (un seul fichier, sans dépendance)
  src/sw.js             service worker (ouverture sans réseau, tuiles gardées)
  src/icons/            icônes
  build.py              assemble dev/dist, publie à la racine, vérifie que la racine correspond à la source
  tests/e2e.py          essai de bout en bout dans un navigateur (écran de téléphone)
  tests/sw.py           essai du service worker
  tests/fixtures/v3/    la version 3 telle qu'elle était publiée : point de départ de l'essai de migration
  donnees/              scripts qui ont produit les listes d'espèces et les noms français
```

## Modifier, essayer, publier

```
python3 dev/build.py                 # assemble dev/dist
python3 dev/tests/e2e.py             # 2 à 3 minutes ; captures dans dev/dist/captures
python3 dev/tests/sw.py
python3 dev/build.py --publier       # copie le résultat à la racine du dépôt
git commit … && git push             # GitHub Pages sert la racine de la branche main
```

Les essais demandent Python, `playwright` (avec Chromium) et `pillow`. Rien d'autre.
`python3 dev/build.py --verifier` échoue si la racine du dépôt n'est pas exactement ce que donne la source.
À chaque version : changer `APP_VERSION` dans `src/app.html` et `VERSION` dans `build.py` (le nom du cache du service worker en dépend).

## Ce que couvrent les essais

`tests/e2e.py` simule le réseau (Open-Meteo, tuiles IGN, position GPS) et bloque tout le reste ; il échoue si une requête part vers un service non prévu ou si une erreur JavaScript survient. Il part d'un carnet créé par la V3 (y compris chiffré par code) et l'ouvre avec la version construite, puis vérifie :

- migration : mêmes fiches, mêmes photos, positions intactes, date de modification inchangée ;
- saisie gardée : frappe, rechargement en pleine saisie, démarrage à froid, retour arrière, reprise, abandon ;
- photos : cinq plans, photothèque, remplacement, retrait, rien d'effacé avant l'enregistrement, nettoyage des orphelines ;
- position : meilleur point de plusieurs, deuxième toucher, point loin du spot, position introuvable, nouveau spot ;
- sauvegarde `.zip` (validée par un autre outil), restauration, archive recompressée, ancienne sauvegarde `.json`, fichiers abîmés ;
- export Darwin Core et GPX, deuxième avis, carte, carte hors ligne, climat, coffre, téléphone plein, stockage refusé ;
- mise en page à 340 px de large, mode sombre.

Ce que ces essais ne peuvent pas dire : le comportement sur un vrai iPhone (appareil photo, feuille de partage, GPS réel) et la réponse des vrais serveurs de l'IGN.

## Données du Mycodex

- **Liste de départ** (78 espèces) : choisie à la main, périodes indicatives en France.
- **Liste Charente** (346 espèces de plus) : `donnees/liste_charente.py`, à partir de la liste d'espèces GBIF du 24 octobre 2026
  (https://www.gbif.org/occurrence/download/0001742-261023074918325). Lichens et micro-champignons écartés.
- **Noms français et identifiants** : TAXREF v18 (PatriNat : OFB, CNRS, MNHN ; Licence Ouverte 2.0).
  Le fichier lu est la conversion Parquet du dépôt https://github.com/Redcozmo/taxref-explorer (`data/taxref.parquet`, 708 685 noms).
  Ce fichier n'indique pas lui-même sa version : le dépôt cite TAXREF v18, et les noms les plus récents qu'il contient datent de 2024, ce qui concorde.

```
node dev/donnees/taxref/pq.js taxref.parquet dump CD_NOM,CD_REF,RANG,LB_NOM,LB_AUTEUR,NOM_VALIDE,NOM_VERN,FR REGNE=Fungi > champignons.tsv
node dev/donnees/taxref/names.js dev/src/app.html > noms.json
python3 dev/donnees/taxref/rattacher.py noms.json champignons.tsv export-gbif.csv rattachements.json
```

`donnees/taxref/rattachements.json` est le résultat : 415 espèces sur 424 rattachées à un taxon de référence, 295 avec au moins un nom français.
Une espèce n'est rattachée que si son nom latin, ou les noms sous lesquels elle a été saisie en Charente, mènent à un seul taxon ; les lignes « sensu … » de TAXREF (noms mal appliqués) sont écartées. Neuf espèces restent sans rattachement plutôt que devinées :
*Tricholomopsis sulphureoides, Hydnellum cristatum, Hydnum magnorufescens, Inocybe dryadiana, Inocybe jacobssonii, Inocybe pyriodora, Leucocoprinus leucothites, Ophiocordyceps larvicola, Pisolithus capsulifer*.
Un seul choix a été fait à la main, noté dans le script : *Tremella mesenterica* (deux lignes homonymes valides dans TAXREF).

## Limites connues

- L'export Darwin Core écrit `stateProvince = Charente` pour toutes les observations, même faites ailleurs.
- La liste GBIF vient de jeux de données qui ont chacun leur licence (sur GBIF : CC0, CC BY ou CC BY-NC). Lesquelles s'appliquent ici se lit sur la page du téléchargement ; à vérifier avant toute vente de l'app.
