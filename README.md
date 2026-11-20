# Mycota — carnet de terrain du mycologue

Adresse : https://sciencewithat-bit.github.io/curly-octo-parakeet/

Tout reste sur le téléphone : spots, sorties, fiches, photos. Aucun compte, aucun serveur à soi.
Ce qui sort du téléphone, et rien d'autre :

- la position arrondie à ~1 km, envoyée à Open-Meteo pour la pluie et la température ;
- les tuiles de carte de la zone affichée, demandées à l'IGN (Plan IGN, photographies aériennes) ou à OpenStreetMap ;
- les fichiers que tu choisis d'envoyer toi-même (sauvegarde, export Darwin Core, image « deuxième avis »).

Mycota n'identifie aucun champignon. Avant toute consommation, fais confirmer par un mycologue ou un pharmacien formé.

## Installer sur l'iPhone

Ouvre l'adresse dans **Safari**, bouton Partager → « Sur l'écran d'accueil ». Ouvre l'app une première fois avec du réseau : ensuite elle démarre sans réseau en forêt.
Pour la carte sans réseau : onglet Carte → « Hors ligne » → Préparer (tuiles IGN dans un rayon d'environ 1 km autour des spots).

## Sauvegarde

Réglages → « Sauvegarde complète » produit une archive `.zip` : `mycota.json` (spots, sorties, fiches, notes) et les photos en fichiers `.jpg`, lisibles sans Mycota.
« Restaurer une sauvegarde » relit cette archive, même défaite puis recompressée, ainsi que les anciennes sauvegardes `.json`.
Installée, l'app n'est plus vidée par Safari, mais le téléphone reste le seul exemplaire de tes relevés : exporte une sauvegarde après tes sorties, l'app te le rappelle.

## Mises à jour

Les nouvelles versions sont poussées sur la branche `main`. L'app se met à jour à l'ouverture suivante avec réseau ; avec un réseau faible, elle s'ouvre sur la version gardée et se met à jour en arrière-plan. Les données déjà saisies sont reprises telles quelles.

## Sources

- Liste Charente : GBIF.org, téléchargement du 24 octobre 2026, https://www.gbif.org/occurrence/download/0001742-261023074918325
- Noms français et identifiants des espèces : TAXREF v18, PatriNat (OFB, CNRS, MNHN), Licence Ouverte 2.0, https://taxref.mnhn.fr/
- Météo : Open-Meteo. Fonds de carte : © IGN (Géoplateforme, Licence Ouverte), © contributeurs OpenStreetMap.

## Développement

Le dossier `dev/` contient la source (`dev/src/app.html`, un seul fichier), le script d'assemblage et les essais automatiques. Voir `dev/LISEZMOI.md`.
Les fichiers à la racine (`index.html`, `sw.js`…) sont le résultat de l'assemblage : on ne les modifie pas à la main.
