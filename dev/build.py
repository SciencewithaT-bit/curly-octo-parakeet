"""Assemble Mycota à partir de dev/src.

  python3 dev/build.py              construit dev/dist (aperçu claude.ai et dossier PWA)
  python3 dev/build.py --publier    construit, puis copie le dossier PWA à la racine du dépôt (ce que sert GitHub Pages)
  python3 dev/build.py --verifier   construit, puis échoue si la racine du dépôt n'est pas exactement ce que donne la source

Aucune dépendance : Python seul."""
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
SITE = ROOT.parent
VERSION = "4.0.0"
PUBLISHED = ["index.html", "sw.js", "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png", ".nojekyll"]

src = (SRC / "app.html").read_text(encoding="utf-8")
m = re.search(r"const APP_VERSION = '(\d+\.\d+)'", src)
if not m or not VERSION.startswith(m.group(1) + "."):
    sys.exit(f"Versions désaccordées : build.py dit {VERSION}, la source dit {m.group(1) if m else '?'}")

# 1. Aperçu claude.ai : la page telle quelle (le squelette est ajouté à la publication).
art = ROOT / "dist" / "artifact"
art.mkdir(parents=True, exist_ok=True)
(art / "mycota.html").write_text(src, encoding="utf-8")

# 2. PWA : document complet.
pwa = ROOT / "dist" / "pwa"
if pwa.exists():
    shutil.rmtree(pwa)
pwa.mkdir(parents=True)
head_part, body_part = src.split("<style>", 1)
body_part = "<style>" + body_part
head_part = re.sub(r'<meta name="claude:[^>]+>\s*', "", head_part)

index = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#F3F4EE" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0F1411" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Mycota">
<meta name="description" content="Carnet de terrain privé du mycologue : spots, sorties, spécimens. Tout reste sur ton téléphone.">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" href="icon-192.png">
{head_part.strip()}
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}img{{max-width:100%}}</style>
</head>
<body>
{body_part.strip()}
</body>
</html>
"""
(pwa / "index.html").write_text(index, encoding="utf-8")
(pwa / "sw.js").write_text((SRC / "sw.js").read_text(encoding="utf-8").replace("__VERSION__", VERSION), encoding="utf-8")
(pwa / "manifest.webmanifest").write_text(json.dumps({
    "name": "Mycota",
    "short_name": "Mycota",
    "description": "Carnet de terrain privé du mycologue.",
    "lang": "fr",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#F3F4EE",
    "theme_color": "#F3F4EE",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}, ensure_ascii=False, indent=2), encoding="utf-8")
for f in sorted((SRC / "icons").glob("*.png")):
    shutil.copy(f, pwa / f.name)
(pwa / ".nojekyll").write_text("", encoding="utf-8")
built = sorted(p.name for p in pwa.iterdir())
if built != sorted(PUBLISHED):
    sys.exit(f"Fichiers construits inattendus : {built}")
print("construit", VERSION, "→", pwa)

if "--publier" in sys.argv:
    for name in PUBLISHED:
        shutil.copy(pwa / name, SITE / name)
    print("publié à la racine du dépôt :", ", ".join(PUBLISHED))

if "--verifier" in sys.argv:
    diff = [name for name in PUBLISHED if not (SITE / name).exists() or (SITE / name).read_bytes() != (pwa / name).read_bytes()]
    if diff:
        sys.exit("La racine du dépôt ne correspond pas à la source pour : " + ", ".join(diff) + ". Lance « python3 dev/build.py --publier ».")
    print("la racine du dépôt est bien ce que donne la source")
