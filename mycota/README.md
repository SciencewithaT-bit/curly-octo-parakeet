# Mycota — version de terrain

Carnet de terrain du mycologue. Tout reste sur le téléphone : aucune donnée n'est envoyée nulle part, à part la position arrondie (~1 km) transmise à Open-Meteo pour la pluie.

## Mettre en ligne (GitHub Pages, gratuit)

1. Crée un dépôt **public** `mycota` sur GitHub (Pages gratuit exige un dépôt public ; le code est public, tes données non, elles restent dans ton téléphone).
2. Dépose le contenu de ce dossier à la racine du dépôt, puis :
   ```bash
   git init && git add -A && git commit -m "Mycota 1.0" && git branch -M main
   git remote add origin git@github.com:SciencewithaT-bit/mycota.git && git push -u origin main
   ```
3. Sur GitHub : Settings → Pages → Source « Deploy from a branch », branche `main`, dossier `/ (root)`.
4. Une minute plus tard : `https://sciencewithat-bit.github.io/mycota/` (le nom exact est affiché dans Settings → Pages).

## Installer sur l'iPhone

Ouvre l'adresse dans **Safari**, bouton Partager → « Sur l'écran d'accueil ». Ouvre l'app une première fois avec du réseau : ensuite elle démarre sans réseau en forêt.

Installée, Safari ne vide plus son stockage. Exporte quand même une sauvegarde complète après tes sorties (Réglages → Sauvegarde).

## Mettre à jour

Remplace les fichiers, change `VERSION` dans `build.py` si tu reconstruis, pousse. L'app se met à jour à l'ouverture suivante avec réseau.
