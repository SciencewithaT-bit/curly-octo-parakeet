"""Mycota — essai de bout en bout dans un vrai navigateur, sur un écran de téléphone.

  python3 dev/build.py && python3 dev/tests/e2e.py [dossier de la V3] [dossier de la V4 construite] [dossier des captures]

Navigateur : Chromium par défaut ; MYCOTA_NAVIGATEUR=webkit pour le moteur de Safari.

Le réseau est simulé : Open-Meteo, tuiles IGN et position GPS sont remplacés par des réponses fixes,
tout le reste est bloqué. L'essai part d'un carnet créé par la V3, l'ouvre avec la V4 sur la même origine
(migration), puis parcourt chaque fonction. Il se termine en erreur si une seule vérification échoue."""
import csv
import datetime
import http.server
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import threading
import zipfile

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OLD = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "fixtures" / "v3"
NEW = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "dist" / "pwa"
SHOTS = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "dist" / "captures"
PORT = 8780
SHOTS.mkdir(parents=True, exist_ok=True)
WORK = pathlib.Path(tempfile.mkdtemp(prefix="mycota-e2e-"))
shutil.copytree(OLD, WORK / "srv" / "old")
shutil.copytree(NEW, WORK / "srv" / "new")
BASE = f"http://127.0.0.1:{PORT}"



class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WORK / "srv"), **k)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

# ---------- images d'essai ----------
IMG = []
for k, (w, h, col) in enumerate([(1400, 1000, (150, 110, 70)), (1000, 1400, (210, 190, 150)), (1200, 900, (90, 120, 80)), (900, 1200, (180, 140, 100)),
                                 (1300, 1300, (120, 90, 60)), (1100, 800, (200, 170, 120)), (800, 1100, (100, 100, 90))]):
    im = Image.new("RGB", (w, h), col)
    ImageDraw.Draw(im).ellipse([w * 0.3, h * 0.3, w * 0.7, h * 0.7], fill=tuple(min(255, c + 40) for c in col))
    path = WORK / f"t{k + 1}.jpg"
    im.save(path, quality=80)
    IMG.append(str(path))

# ---------- réseau simulé ----------
today = datetime.date.today()
days = [(today - datetime.timedelta(days=30 - i)).isoformat() for i in range(38)]
mm = [((i * 7) % 11) * 0.8 for i in range(38)]
mm[18] = 22.4
METEO = {"daily": {"time": days, "precipitation_sum": mm, "temperature_2m_max": [14 + i % 4 for i in range(38)], "temperature_2m_min": [6 + i % 3 for i in range(38)]}}


def tile(kind):
    im = Image.new("RGB", (256, 256), (236, 238, 228) if kind == "plan" else (86, 112, 70))
    d = ImageDraw.Draw(im)
    for k in range(0, 256, 64):
        d.line([(0, k + 20), (256, k + 40)], fill=(190, 205, 180) if kind == "plan" else (60, 90, 52), width=3)
    d.line([(30, 0), (200, 256)], fill=(250, 250, 250) if kind == "plan" else (120, 140, 100), width=4)
    b = io.BytesIO()
    im.save(b, "PNG" if kind == "plan" else "JPEG")
    return b.getvalue()


TILES = {"plan": tile("plan"), "ortho": tile("ortho")}
calls = {"ign": 0, "pm019": 0, "pm": 0, "meteo": 0, "autres": []}
FAIL_PM019 = [False]


def route(r):
    u = r.request.url
    if "open-meteo" in u:
        calls["meteo"] += 1
        return r.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"}, body=json.dumps(METEO))
    if "data.geopf.fr" in u:
        calls["ign"] += 1
        if FAIL_PM019[0] and "TILEMATRIXSET=PM_0_19" in u:
            calls["pm019"] += 1
            return r.fulfill(status=400, body="bad matrix", headers={"Access-Control-Allow-Origin": "*"})
        if "TILEMATRIXSET=PM&" in u:
            calls["pm"] += 1
        kind = "ortho" if "ORTHOIMAGERY" in u else "plan"
        return r.fulfill(status=200, content_type="image/png" if kind == "plan" else "image/jpeg", headers={"Access-Control-Allow-Origin": "*"}, body=TILES[kind])
    if u.startswith(BASE):
        return r.continue_()
    if "fonts.g" not in u and "openstreetmap" not in u:
        calls["autres"].append(u)
    return r.abort()


# Position simulée. localStorage.__geo règle le lieu, la suite des précisions reçues et leur rythme.
GEO = """
try { Object.defineProperty(Navigator.prototype, 'canShare', { configurable: true, value: undefined }); } catch (e) {}
(() => {
  const cfg = () => { try { return JSON.parse(localStorage.getItem('__geo') || 'null') || {}; } catch { return {}; } };
  const fix = acc => { const c = cfg(); return { coords: { latitude: c.lat ?? 45.69361, longitude: c.lng ?? 0.29162, accuracy: acc, altitude: 118.4, altitudeAccuracy: 4, heading: null, speed: null }, timestamp: Date.now() }; };
  const g = navigator.geolocation; let wid = 0; const timers = {};
  g.getCurrentPosition = (ok, err) => { const c = cfg(); setTimeout(() => c.fail ? err && err({ code: 2 }) : ok(fix((c.seq || [7])[0])), 40); };
  g.watchPosition = (ok, err) => {
    const c = cfg(), id = ++wid, seq = c.seq || [7], step = c.step || 300;
    timers[id] = c.fail ? [setTimeout(() => err && err({ code: 2 }), 40)] : seq.map((a, i) => setTimeout(() => ok(fix(a)), 40 + i * step));
    return id;
  };
  g.clearWatch = id => { (timers[id] || []).forEach(clearTimeout); delete timers[id]; };
})();
"""

errors, results = [], {}


def check(name, cond, info=""):
    results[name] = bool(cond)
    print(("OK   " if cond else "FAIL ") + name, f"· {info}" if info != "" else "", flush=True)


with sync_playwright() as p:
    ENGINE = os.environ.get("MYCOTA_NAVIGATEUR", "chromium")
    b = getattr(p, ENGINE).launch()
    print("navigateur :", ENGINE, b.version, flush=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="fr-FR", timezone_id="Europe/Paris", accept_downloads=True)
    ctx.add_init_script(GEO)
    ctx.route("**/*", route)
    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text and "net::ERR" not in m.text else None)
    pg.on("pageerror", lambda e: errors.append("PAGEERROR " + str(e)))
    ev = pg.evaluate
    wait = pg.wait_for_timeout

    def shot(n, full=False):
        pg.screenshot(path=str(SHOTS / f"{n}.png"), full_page=full)

    def geo(**k):
        ev("c => localStorage.setItem('__geo', JSON.stringify(c))", k)

    def nav(view, params="{}"):
        ev(f"parkDraft(); go('{view}', {params})")
        wait(350)

    def sheet_open():
        return pg.locator("#scrim").count() == 1

    def toast_text():
        return ev("(() => { const t = document.querySelector('.toast'); return t && !t.hidden ? t.textContent : ''; })()")

    def photo_ids():
        return set(ev("DB.all('photos').then(a => a.map(p => p.id))"))

    MKPHOTO = """async (rgb) => { const c = document.createElement('canvas'); c.width = 900; c.height = 700; const x = c.getContext('2d'); x.fillStyle = rgb; x.fillRect(0, 0, 900, 700);
      x.fillStyle = '#fff'; x.fillRect(300, 200, 300, 300); const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.8)); return addPhoto(new File([blob], 'x.jpg', { type: 'image/jpeg' })); }"""

    # =====================================================================
    # A. Carnet créé par la V3, ouvert par la V4 sur la même origine
    # =====================================================================
    pg.goto(f"{BASE}/old/index.html")
    wait(700)
    pg.click("text=Voir avec des exemples")
    pg.click("[data-x=ok]")
    wait(600)
    pa, pb, pc, pd_ = [ev(MKPHOTO, c) for c in ("#8a5a2b", "#c9b089", "#55703f", "#333333")]
    ev("""async ([pa, pb, pc, pd]) => {
      await saveRec('spot', { id: 'real1', name: 'Mon coin perso', forest: 'Hêtraie', notes: '', lat: 45.7, lng: 0.3 });
      await saveRec('sortie', { id: 'realo', spotId: 'real1', date: '2026-10-20T09:00', photoIds: [pc], meteo: { sol: 'Frais', ciel: [], text: '' }, notes: 'v3 réel', wx: { mm: 30.5, t: 11.2, days: 10, at: 1, v: 2 },
        obs: [{ species: 'Pied bleu', latin: 'Lepista nuda', count: 4, weight: '', photos: { chapeau: pa }, certitude: 'Probable', methodes: ['Macroscopie'], hote: 'Fagus sylvatica', capMin: '40', capMax: '90', sporee: 'Rose', odeur: 'Fruitée', lat: 45.70012, lng: 0.30034, acc: 9, alt: 97 },
              { species: 'Laccaire améthyste', latin: 'Laccaria amethystina', count: 12, weight: '', photos: {} }] });
      await saveRec('specimen', { id: 'realm', date: '2026-10-20T15:00', spotId: 'real1', photos: { chapeau: pb }, extra: [pd], odeur: 'Farine', sporee: '', hypothese: 'Clitocybe nébuleux', latin: 'Clitocybe nebularis', notes: '', status: 'a_identifier' });
    }""", [pa, pb, pc, pd_])
    ev("(async () => { S.taxnotes['fausse girolle'] = 'Lames fourchues, chair molle.'; await metaPut('taxnotes', S.taxnotes); })()")
    wait(300)
    SNAP = "[S.spots.length, S.sorties.length, S.specimens.length, JSON.stringify(S.sorties.find(s => s.id === 'realo').obs), S.sorties.find(s => s.id === 'realo').updatedAt]"
    old = ev(SNAP)
    old_photos = photo_ids()
    ev("go('reglages', {})")
    wait(300)
    pg.click("[data-act=exportJSON]")
    pg.wait_for_selector("#of-go", timeout=15000)
    with pg.expect_download() as d:
        pg.click("#of-go")
    V3_JSON = str(WORK / "sauvegarde-v3.json")
    d.value.save_as(V3_JSON)
    check("V3 : sauvegarde .json produite", json.load(open(V3_JSON))["format"] == 3)

    pg.goto(f"{BASE}/new/index.html")
    wait(1200)
    new = ev(SNAP)
    check("migration : mêmes nombres de spots, sorties, spécimens", old[:3] == new[:3], f"{old[:3]} -> {new[:3]}")
    o_old, o_new = json.loads(old[3]), json.loads(new[3])
    check("migration : observations intactes, identifiant en plus", [{k: v for k, v in o.items() if k != "id"} for o in o_new] == o_old and [o["id"] for o in o_new] == ["realo:0", "realo:1"], str([o.get("id") for o in o_new]))
    check("migration : identifiants écrits dans le téléphone", [o.get("id") for o in ev("DB.get('sorties', 'realo')")["obs"]] == ["realo:0", "realo:1"])
    check("migration : date de modification inchangée", old[4] == new[4])
    check("migration : photos toutes présentes", photo_ids() == old_photos and len(old_photos) == 4, str(len(old_photos)))
    check("version affichée 4.0", ev("APP_VERSION") == "4.0")
    ev("(async () => { await DB.del('meta', 'backup'); S.backup = null; })()")   # pour la suite : comme si aucune sauvegarde n'avait encore été faite
    check("migration : une note rangée sous un nom français suit l'espèce désormais reconnue", ev("S.taxnotes['hygrophoropsis aurantiaca']") == "Lames fourchues, chair molle." and ev("'fausse girolle' in S.taxnotes") is False)
    ev("go('obs', { sid: 'realo', i: 0 })")
    wait(400)
    check("ancien lien de fiche (par rang) toujours lisible", pg.input_value("#o-la") == "Lepista nuda")
    nav("carnet")

    # =====================================================================
    # B. Ce qui existait en V3
    # =====================================================================
    shot("01-carnet")
    shot("01b-carnet-entier", True)
    check("mémoire de terrain", pg.locator("text=Mémoire de terrain").count() == 1 and pg.locator("text=Il y a un an").count() >= 1 and pg.locator("text=À revoir").count() >= 1)
    check("pas de rappel de sauvegarde après une seule sortie réelle", pg.locator(".notice.backup").count() == 0)
    pg.click("text=Bilan de la saison")
    wait(400)
    shot("02-bilan", True)
    check("bilan : douze barres, plusieurs années", pg.locator(".mbar").count() == 12 and pg.locator("[data-act=bilanYear]").count() >= 2)
    pg.click("[data-act=bilanYear] >> nth=1")
    wait(300)
    check("bilan : année précédente", "bilan 2025" in pg.inner_text(".bar-title").lower())
    pg.click("[data-act=back]")
    wait(300)

    # ---------- Mycodex : silhouettes, tri, recherche ----------
    pg.click(".tab[data-v=codex]")
    wait(400)
    caps = ev("[...document.querySelectorAll('#dex-list .dexsec')].map(s => { const g = s.querySelector('svg.shroom'); const p = g ? [...g.children].filter(c => c.tagName.toLowerCase() === 'path') : []; return p.length ? p[p.length - 1].getAttribute('d') : null; })")
    check("Mycodex : une silhouette différente pour chacun des 9 groupes", len(caps) == 9 and len(set(caps)) == 9 and None not in caps, f"{len(set(caps))} silhouettes")
    shot("03-mycodex", True)
    pg.select_option("#dex-sort", "gb")
    wait(200)
    first = pg.inner_text("#dex-list .dex >> nth=0 >> .cell >> nth=0")
    check("Mycodex : tri par mentions en Charente", "aereus" in first or "bronzé" in first, first.replace("\n", " | "))
    pg.select_option("#dex-sort", "num")
    pg.fill("#dex-q", "girolle")
    wait(450)
    check("Mycodex : recherche", pg.locator("#dex-list .cell").count() == 1, str(pg.locator("#dex-list .cell").count()))
    found = {}
    for q in ("cepe de bordeaux", "oronge verte", "palomet"):
        pg.fill("#dex-q", q)
        wait(400)
        found[q] = [c.split("\n")[-2] if "Charente" in c.split("\n")[-1] else c.split("\n")[-1] for c in pg.locator("#dex-list .cell").all_inner_texts()]
    check("Mycodex : recherche sans accents et par un autre nom français (TAXREF)", found == {"cepe de bordeaux": ["Boletus edulis"], "oronge verte": ["Amanita phalloides"], "palomet": ["Russula virescens"]}, str(found))
    pg.fill("#dex-q", "")
    wait(300)
    pg.click("[data-act=dexList][data-val=charente]")
    wait(500)
    n_cells, n_latin_only = pg.locator("#dex-list .cell").count(), pg.locator("#dex-list .cell-fr.la").count()
    check("Mycodex : liste Charente complète, 296 espèces sur 424 avec un nom français", n_cells == 424 and n_latin_only == 128, f"{n_cells} cases, {n_latin_only} en latin seul")
    pg.fill("#dex-q", "fausse girolle")
    wait(400)
    txt = pg.locator("#dex-list .cell").all_inner_texts()
    check("Mycodex Charente : nom français officiel affiché", len(txt) == 1 and "Fausse girolle" in txt[0] and "Hygrophoropsis aurantiaca" in txt[0], str(txt))
    pg.fill("#dex-q", "")
    wait(300)
    pg.click("[data-act=dexList][data-val=depart]")
    wait(300)

    # ---------- fiche espèce ----------
    nav("taxon", "{ key: 'boletus edulis' }")
    check("fiche espèce : phénologie, décalage, conditions", pg.locator("text=Par saison").count() == 1 and pg.locator("text=Première pousse").count() == 1 and pg.locator("text=Conditions de tes trouvailles").count() == 1)
    pg.fill("[data-taxnote]", "Réseau blanc en haut du pied. Écarter le bolet amer : réseau brun, chair amère.")
    wait(700)
    shot("04-espece", True)
    nav("taxon", "{ key: 'amanita phalloides' }")
    body = pg.inner_text("#app")
    check("fiche espèce : autres noms français et numéro TAXREF", "Aussi : Oronge verte" in body and "TAXREF n° 39106" in body, body[:120].replace("\n", " | "))
    nav("taxon", "{ key: 'inocybe pyriodora' }")
    check("espèce non rattachée à TAXREF : dit clairement", "Pas de rattachement à TAXREF" in pg.inner_text("#app"))
    ev("parkDraft(); go('sortieForm', { spotId: 'demo-s1' })")
    wait(400)
    got = []
    for typed in ("Colombette", "cepe de bordeaux", "Jaunet"):
        pg.fill("#la-0", "")
        pg.fill("[data-sp='0']", typed)
        pg.dispatch_event("[data-sp='0']", "change")
        got.append(pg.input_value("#la-0"))
    check("saisie : un nom français officiel, même sans accents, retrouve le nom latin ; un nom partagé par deux espèces n'en désigne aucune", got == ["Tricholoma columbetta", "Boletus edulis", ""], str(got))
    pg.click("[data-act=back]")
    wait(250)
    pg.click("#scrim [data-x=leave]")
    wait(400)

    # =====================================================================
    # C. Saisie gardée : fermeture de l'app, retour arrière, reprise
    # =====================================================================
    nav("carnet")
    pg.click(".fab")
    wait(600)
    check("Noter : position et spot proche annoncés", "±7 m" in pg.inner_text("#note-pos") and "Chênaie du Puits-Rond" in pg.inner_text("#note-near"), pg.inner_text("#note-pos"))
    pg.click("[data-x=sortie]")
    wait(400)
    check("sortie : spot proche présélectionné", pg.input_value("#f-spot") == "demo-s1")
    pg.click("[data-act=back]")
    wait(300)
    check("formulaire non modifié : retour sans question", not sheet_open() and ev("S.view") == "carnet")
    pg.click(".fab")
    wait(500)
    pg.click("[data-x=sortie]")
    wait(400)
    pg.fill("[data-sp='0']", "Girolle")
    pg.dispatch_event("[data-sp='0']", "change")
    wait(900)
    dr = ev("DB.get('meta', 'draft')")
    check("saisie gardée dès la frappe", bool(dr) and dr["value"]["draft"]["obs"][0]["species"] == "Girolle" and dr["value"]["view"] == "sortieForm")
    pg.reload()
    wait(1000)
    check("app rechargée en pleine saisie : formulaire rouvert tel quel", ev("S.view") == "sortieForm" and pg.input_value("[data-sp='0']") == "Girolle" and pg.input_value("#la-0") == "Cantharellus cibarius", toast_text())
    pg.goto("about:blank")   # app fermée puis rouverte : plus d'écran mémorisé par le navigateur
    pg.goto(f"{BASE}/new/index.html")
    wait(1000)
    check("démarrage à froid : saisie proposée sur le Carnet", ev("S.view") == "carnet" and pg.locator(".notice.pending").count() == 1 and "Sortie du" in pg.inner_text(".notice.pending"), pg.inner_text(".notice.pending") if pg.locator(".notice.pending").count() else f"vue {ev('S.view')}, en attente : {ev('!!S.pendingDraft')}")
    shot("05-carnet-saisie-en-attente")
    pg.click("[data-act=draftResume]")
    wait(400)
    check("reprise : la saisie revient", ev("S.view") == "sortieForm" and pg.input_value("[data-sp='0']") == "Girolle")
    pg.click("[data-act=back]")
    wait(300)
    check("retour avec saisie modifiée : question posée", sheet_open() and "Quitter sans enregistrer" in pg.inner_text("#scrim"))
    shot("06-quitter-sans-enregistrer")
    pg.click("#scrim [data-x=stay]")
    wait(200)
    check("« Continuer la saisie » : on reste", ev("S.view") == "sortieForm" and not sheet_open())
    pg.click("[data-act=back]")
    wait(200)
    pg.click("#scrim [data-x=leave]")
    wait(500)
    check("« Quitter » : saisie jetée", ev("S.view") == "carnet" and ev("S.pendingDraft") is None and ev("DB.get('meta', 'draft')") is None)

    # retour arrière du téléphone : la saisie reste gardée, une autre fiche demande d'abord
    pg.click(".fab")
    wait(500)
    pg.click("[data-x=sortie]")
    wait(400)
    pg.fill("[data-sp='0']", "Cèpe de Bordeaux")
    pg.dispatch_event("[data-sp='0']", "change")
    ev("history.back()")
    wait(600)
    check("geste retour du téléphone : saisie gardée", ev("S.view") == "carnet" and pg.locator(".notice.pending").count() == 1 and ev("S.pendingDraft.draft.obs[0].latin") == "Boletus edulis")
    pg.click("[data-act=go][data-v=spotForm] >> nth=0")
    wait(400)
    check("autre formulaire : on demande avant d'écraser la saisie gardée", sheet_open() and "saisie non enregistrée" in pg.inner_text("#scrim").lower() and ev("S.view") == "carnet")
    shot("07-saisie-en-attente-question")
    pg.click("#scrim [data-x=drop]")
    wait(700)
    check("« La jeter et continuer »", ev("S.view") == "spotForm" and ev("S.pendingDraft") is None)
    pg.click("[data-act=back]")
    wait(400)
    check("nouveau spot non modifié : retour sans question", not sheet_open() and ev("S.view") == "carnet")
    ev("S.lastPos = null")
    nav("spotForm", "{ here: true }")
    pg.wait_for_function("S.draft && typeof S.draft.lat === 'number' && S.draft.acc === 7", timeout=5000)
    wait(700)
    check("nouveau spot : position prise toute seule à l'ouverture, sans compter comme une modification", ev("isDirty()") is False and ev("S.pendingDraft") is None and "±7 m" in pg.inner_text("#pick-coords"), pg.inner_text("#pick-coords"))
    pg.fill("#f-name", "Coin des trompettes")
    wait(800)
    check("nouveau spot : la saisie du nom est gardée", ev("S.pendingDraft && S.pendingDraft.draft.name") == "Coin des trompettes")
    pg.click("[data-act=saveSpot]")
    wait(600)
    check("spot créé, plus rien en attente", ev("S.view") == "spot" and ev("S.spots.some(s => s.name === 'Coin des trompettes' && s.alt === 118)") and ev("S.pendingDraft") is None)
    ev("(async () => { await deleteRec('spot', S.params.id); go('carnet', {}, { replace: true }); })()")
    wait(400)
    for view, params in [("obs", "{ sid: 'demo-o2', oid: 'demo-o2:0' }"), ("sortieForm", "{ id: 'demo-o0' }"), ("spotForm", "{ id: 'demo-s1' }"), ("specimen", "{ id: 'demo-m1' }"), ("specimen", "{}")]:
        nav(view, params)
        wait(300)
        pg.click("[data-act=back]")
        wait(350)
        check(f"ouvrir puis quitter sans rien changer : {view} {params}", not sheet_open() and ev("S.pendingDraft") is None and ev("S.view") != view, ev("S.view"))
        if sheet_open():
            pg.click("#scrim [data-x=leave]")
            wait(300)

    # la même fiche rouverte retrouve sa saisie
    nav("sortie", "{ id: 'demo-o0' }")
    pg.click("[data-act=obs][data-oid='demo-o0:1']")
    wait(400)
    pg.fill("#o-ouv", "Courtecuisse, p. 318")
    wait(800)
    ev("history.back()")
    wait(500)
    pg.click("[data-act=obs][data-oid='demo-o0:1']")
    wait(400)
    check("même fiche rouverte : saisie retrouvée sans question", not sheet_open() and pg.input_value("#o-ouv") == "Courtecuisse, p. 318", toast_text())
    pg.click("[data-act=saveObs]")
    wait(600)
    check("fiche enregistrée, plus rien en attente", ev("S.sorties.find(s => s.id === 'demo-o0').obs[1].ouvrage") == "Courtecuisse, p. 318" and ev("S.pendingDraft") is None and ev("DB.get('meta', 'draft')") is None)

    # =====================================================================
    # D. Photos : cinq plans, photothèque, retrait, rien d'effacé avant l'enregistrement
    # =====================================================================
    nav("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }")
    check("fiche démo : point présent", pg.locator("text=Reprendre").count() == 1)
    pct0 = pg.inner_text("#o-pct")
    pg.click(".chip[data-path='o.prelev'][data-val='Prélevé pour détermination']")
    wait(150)
    pg.fill("#o-rec", "SA-2026-014")
    pg.set_input_files("label.plan [data-photo-in='obs:chapeau']", IMG[0])
    pg.wait_for_selector("button.plan[data-target='obs:chapeau']", timeout=8000)
    p1 = ev("S.draft.o.photos.chapeau")
    check("plan photo : case remplie, jauge mise à jour sans tout redessiner", bool(p1) and pg.inner_text("#o-pct") != pct0 and pg.input_value("#o-rec") == "SA-2026-014", f"{pct0} -> {pg.inner_text('#o-pct')}")
    pg.click("button.plan[data-target='obs:chapeau']")
    wait(300)
    check("plan rempli : voir, reprendre, photothèque, retirer", sheet_open() and pg.locator("#scrim [data-x=view]").count() == 1 and pg.locator("#scrim [data-photo-in='obs:chapeau']").count() == 2 and pg.locator("#scrim [data-x=del]").count() == 1)
    shot("08-plan-photo-choix")
    pg.click("#scrim [data-x=del]")
    wait(300)
    check("photo retirée de la fiche mais pas encore effacée du téléphone", pg.locator("label.plan [data-photo-in='obs:chapeau']").count() == 1 and p1 in photo_ids())
    pg.set_input_files("[data-photo-in='obs:*']", IMG[:6])
    pg.wait_for_function("Object.keys(S.draft.o.photos).length === 5", timeout=15000)
    wait(300)
    check("photothèque : cinq photos rangées dans les cinq plans, la sixième laissée de côté", "1 photo laissée de côté" in toast_text(), toast_text())
    lames_old = ev("S.draft.o.photos.lames")
    pg.click("button.plan[data-target='obs:lames']")
    wait(250)
    pg.set_input_files("#scrim [data-photo-in='obs:lames'][capture]", IMG[6])
    pg.wait_for_function("old => S.draft && S.draft.o.photos.lames !== old", arg=lames_old, timeout=8000)
    wait(300)
    check("photo reprise : la précédente n'est pas effacée avant l'enregistrement", lames_old in photo_ids() and not sheet_open())
    shot("09-fiche-observation", True)
    pg.click("[data-act=saveObs]")
    wait(700)
    o = ev("S.sorties.find(s => s.id === 'demo-o0').obs[0]")
    check("fiche enregistrée : cinq plans, prélèvement, n° de récolte", len(o["photos"]) == 5 and o.get("prelev") == "Prélevé pour détermination" and o.get("recnum") == "SA-2026-014")
    nav("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }")
    pied = ev("S.draft.o.photos.pied")
    pg.click("button.plan[data-target='obs:pied']")
    wait(250)
    pg.click("#scrim [data-x=del]")
    wait(250)
    pg.click("[data-act=saveObs]")
    wait(700)
    check("photo retirée puis fiche enregistrée : effacée du téléphone à ce moment-là", pied not in photo_ids() and "pied" not in ev("S.sorties.find(s => s.id === 'demo-o0').obs[0].photos"))
    # nettoyage des photos orphelines : seulement les vieilles
    ev("async id => { const p = await DB.get('photos', id); p.createdAt = new Date(Date.now() - 3 * 864e5).toISOString(); await DB.put('photos', p); }", p1)
    before = photo_ids()
    swept = ev("sweepPhotos()")
    after = photo_ids()
    kept_refs = set(ev("[...S.spots, ...S.sorties, ...S.specimens].flatMap(photosOfRec)"))
    check("nettoyage : seule la photo orpheline de plus de deux jours part", swept == 1 and before - after == {p1} and lames_old in after and kept_refs <= after, f"{swept} effacée(s)")

    # =====================================================================
    # E. Point GPS : le meilleur de plusieurs, deuxième toucher, garde-fou loin du spot
    # =====================================================================
    nav("carnet")
    geo(seq=[40, 22, 12, 6], step=400)
    ev("parkDraft(); go('sortieForm', { spotId: 'demo-s1' })")
    wait(400)
    pg.fill("[data-sp='0']", "Craterellus tubaeformis")
    pg.dispatch_event("[data-sp='0']", "change")
    check("nom latin saisi : nom français retrouvé", pg.input_value("[data-sp='0']") == "Chanterelle en tube" and pg.input_value("#la-0") == "Craterellus tubaeformis")
    pg.click("[data-act=obsPin][data-i='0']")
    wait(250)
    live = pg.inner_text("[data-act=obsPin][data-i='0'] span")
    pg.wait_for_function("document.querySelector('[data-act=obsPin][data-i=\"0\"]').getAttribute('aria-pressed') === 'true'", timeout=8000)
    final = pg.inner_text("[data-act=obsPin][data-i='0'] span")
    check("point : précision affichée pendant l'affinage, meilleur point gardé", live == "±40 m…" and final == "±6 m" and ev("S.draft.obs[0].acc") == 6 and ev("S.draft.obs[0].alt") == 118, f"{live} puis {final}")
    pg.click("text=+ Ajouter une espèce")
    wait(200)
    pg.fill("[data-sp='1']", "Hydnum rufescens")
    pg.dispatch_event("[data-sp='1']", "change")
    geo(seq=[40, 30, 25, 20, 15, 14, 13], step=500)
    pg.click("[data-act=obsPin][data-i='1']")
    wait(800)
    pg.click("[data-act=obsPin][data-i='1']")
    wait(300)
    acc = ev("S.draft.obs[1].acc")
    check("deuxième toucher : le meilleur point déjà reçu est pris tout de suite", acc == 30 and pg.inner_text("[data-act=obsPin][data-i='1'] span") == "±30 m", str(acc))
    pg.click("text=+ Ajouter une espèce")
    wait(200)
    pg.fill("[data-sp='2']", "Morchella esculenta")
    pg.dispatch_event("[data-sp='2']", "change")
    # ligne avec un point mais sans nom : rien n'est jeté en silence
    pg.click("text=+ Ajouter une espèce")
    wait(200)
    geo(seq=[7])
    pg.click("[data-act=obsPin][data-i='3']")
    pg.wait_for_function("S.draft.obs[3] && typeof S.draft.obs[3].lat === 'number'", timeout=5000)
    n0 = ev("S.sorties.length")
    pg.click("[data-act=saveSortie]")
    wait(400)
    check("observation avec point mais sans nom : l'enregistrement s'arrête et le dit", ev("S.view") == "sortieForm" and ev("S.sorties.length") == n0 and "pas de nom" in toast_text(), toast_text())
    pg.click("[data-act=obsDel][data-i='3']")
    wait(250)
    check("retirer une observation qui a déjà son point : confirmation", sheet_open() and "Retirer cette observation" in pg.inner_text("#scrim"))
    pg.click("#scrim [data-x=ok]")
    wait(300)
    check("observation retirée", ev("S.draft.obs.length") == 3)
    # loin du spot : question, puis refus
    geo(lat=45.75, lng=0.35, seq=[7])
    pg.click("[data-act=obsPin][data-i='2']")
    pg.wait_for_selector("#scrim", timeout=5000)
    check("point pris loin du spot : question posée", "du spot" in pg.inner_text("#scrim h2") and "km" in pg.inner_text("#scrim h2"), pg.inner_text("#scrim h2"))
    shot("10-loin-du-spot")
    pg.click("#scrim [data-x=no]")
    wait(300)
    check("« Ne pas le prendre » : pas de point", ev("S.draft.obs[2].lat") is None and pg.inner_text("[data-act=obsPin][data-i='2'] span") == "Point")
    shot("11-sortie-formulaire", True)
    # double toucher sur Enregistrer : une seule sortie
    ev("(() => { const b = document.querySelector('[data-act=saveSortie]'); b.click(); b.click(); })()")
    wait(1300)
    check("double toucher sur « Enregistrer » : une seule sortie créée", ev("S.sorties.length") == n0 + 1, f"{n0} -> {ev('S.sorties.length')}")
    check("nouvelle case : feuille de révélation", sheet_open() and pg.locator("#scrim .reveal").count() == 1 and "3 nouvelles cases" in pg.inner_text("#scrim .reveal").lower(), pg.inner_text("#scrim .reveal .ribbon") if pg.locator("#scrim .reveal").count() else "")
    shot("12-nouvelles-cases")
    pg.click("#rv-ok")
    wait(300)
    so = ev("S.sorties.find(s => s.id === S.params.id)")
    check("sortie : identifiants stables, points par observation", all(o["id"].startswith("b") for o in so["obs"]) and len({o["id"] for o in so["obs"]}) == 3 and so["obs"][0].get("acc") == 6 and "lat" not in so["obs"][2])
    check("sortie saisie loin du spot : pas de position de sortie (le spot sert de repli)", "lat" not in so, str({k: so.get(k) for k in ("lat", "lng")}))
    pg.wait_for_function("S.sorties.find(s => s.id === S.params.id).wx", timeout=8000)
    so = ev("S.sorties.find(s => s.id === S.params.id)")
    check("sortie : pluie et température des 10 jours ajoutées", so["wx"].get("v") == 2 and isinstance(so["wx"].get("t"), (int, float)), str(so.get("wx")))
    shot("13-sortie", True)
    SID = so["id"]
    # une seule nouvelle case
    geo(seq=[7])
    ev("parkDraft(); go('sortieForm', { spotId: 'demo-s1' })")
    wait(400)
    pg.click("[data-act=obsPin][data-i='0']")
    pg.wait_for_function("S.draft.obs[0] && typeof S.draft.obs[0].lat === 'number'", timeout=5000)
    pg.fill("[data-sp='0']", "Amanite phalloïde")
    pg.dispatch_event("[data-sp='0']", "change")
    pg.click("[data-act=saveSortie]")
    wait(900)
    check("une nouvelle case : nom latin, numéro, silhouette du groupe", sheet_open() and "Amanita phalloides" in pg.inner_text("#scrim .reveal") and pg.locator("#scrim .reveal svg.stamp").count() == 1)
    shot("14-nouvelle-case")
    pg.click("#rv-ok")
    wait(200)
    so2 = ev("S.sorties.find(s => s.id === S.params.id)")
    check("sortie saisie sur place et sur le moment : position de la sortie gardée", so2.get("lat") == 45.69361 and so2.get("alt") == 118)
    ev("parkDraft(); go('sortieForm', { spotId: 'demo-s1' })")
    wait(400)
    pg.fill("[data-sp='0']", "Girolle")
    pg.dispatch_event("[data-sp='0']", "change")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT10:30")
    pg.fill("#f-date", yesterday)
    pg.click("[data-act=saveSortie]")
    wait(900)
    so3 = ev("S.sorties.find(s => s.id === S.params.id)")
    check("sortie d'hier saisie aujourd'hui : la position du téléphone n'est pas prise", "lat" not in so3 and so3["date"] == yesterday and not sheet_open(), toast_text())
    # nouveau spot à ma position : créé là où la saisie a commencé
    geo(lat=45.80, lng=0.40, seq=[7])
    nav("carnet")
    pg.click(".fab")
    pg.wait_for_function("document.querySelector('#note-near') && document.querySelector('#note-near').textContent.includes('aucun spot')", timeout=5000)
    pg.click("[data-x=sortie]")
    wait(400)
    check("loin de tout spot : « nouveau spot à ma position » proposé, position retenue", pg.input_value("#f-spot") == "__new" and ev("S.draft.newSpotPos && S.draft.newSpotPos.lat") == 45.80)
    pg.fill("[data-bind=newSpotName]", "Talus aux girolles")
    pg.fill("[data-sp='0']", "Girolle")
    pg.dispatch_event("[data-sp='0']", "change")
    geo(lat=45.81, lng=0.41, seq=[7])
    ev("(() => { S.lastPos.at = Date.now() - 6 * 60e3; })()")   # le temps passe, on a marché
    pg.click("[data-act=saveSortie]")
    wait(900)
    sp_new = ev("S.spots.find(s => s.name === 'Talus aux girolles')")
    check("nouveau spot créé là où la saisie a commencé, pas là où l'on enregistre", bool(sp_new) and sp_new["lat"] == 45.80 and sp_new["lng"] == 0.40 and ev("S.sorties.find(s => s.id === S.params.id).spotId") == sp_new["id"], str(sp_new and (sp_new["lat"], sp_new["lng"])))
    geo(seq=[7])
    nav("carnet")
    check("rappel de sauvegarde après plusieurs sorties réelles", pg.locator(".notice.backup").count() == 1)
    shot("15-carnet-rappel")

    # ---------- fiche : point repris, puis refusé loin du spot ----------
    nav("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }")
    pg.click("[data-act=oClear]")
    wait(200)
    pg.click("[data-act=oHere]")
    pg.wait_for_function("S.draft && typeof S.draft.o.lat === 'number'", timeout=5000)
    wait(200)
    pt = pg.inner_text(".fgrid:has-text('Point')")
    check("fiche : point repris avec altitude", "alt. 118 m" in pt and "±7 m" in pt, pt.replace("\n", " "))
    pg.click("[data-act=saveObs]")
    wait(600)

    # =====================================================================
    # F. Spécimens : photo rapide, cinq plans, point loin du spot, versement dans une sortie
    # =====================================================================
    nav("carnet")
    pg.click(".fab")
    wait(500)
    pg.set_input_files("[data-quick]", IMG[0])
    pg.wait_for_function("S.view === 'specimen' && S.specimens.some(s => s.quick)", timeout=10000)
    wait(300)
    q = ev("S.specimens.find(s => s.quick)")
    check("photo rapide : spécimen créé avec photo, point et spot proche", bool(q["photos"].get("chapeau")) and q.get("alt") == 118 and q.get("spotId") == "demo-s1" and "±7 m" in toast_text(), toast_text())
    shot("16-photo-rapide", True)
    nav("specimen", "{}")
    pg.set_input_files("[data-photo-in='step:*']", IMG)
    pg.wait_for_function("Object.keys(S.draft.photos).length === 5 && S.draft.extra.length === 2", timeout=20000)
    check("spécimen : photothèque rangée dans les cinq plans, le reste en prises libres", True)
    pg.fill("#f-hyp", "Pied bleu")
    pg.dispatch_event("#f-hyp", "change")
    shot("17-specimen", True)
    # point loin du spot choisi
    ev("syncDraft(); Object.assign(S.draft, { lat: 45.75, lng: 0.35, acc: 8 }); delete S.draft.alt; render()")
    pg.select_option("#f-spot2", "demo-s1")
    n_spec = ev("S.specimens.length")
    pg.click("[data-act=saveSpecimen]")
    pg.wait_for_selector("#scrim", timeout=4000)
    check("spécimen : point loin du spot choisi, question à l'enregistrement", "Ce point est à" in pg.inner_text("#scrim h2"), pg.inner_text("#scrim h2"))
    shot("18-specimen-point-loin")
    pg.mouse.click(195, 60)
    wait(400)
    check("feuille fermée sans répondre : rien n'est enregistré", not sheet_open() and ev("S.specimens.length") == n_spec and ev("S.view") == "specimen")
    pg.click("[data-act=saveSpecimen]")
    pg.wait_for_selector("#scrim", timeout=4000)
    pg.click("#scrim [data-x=ok]")
    wait(700)
    spm = ev("S.specimens.find(s => s.id === S.params.id)")
    check("« Le garder » : spécimen enregistré avec son point", spm.get("lat") == 45.75 and bool(spm.get("farOk")) and len(spm["photos"]) == 5 and len(spm["extra"]) == 2)
    pg.click(".chip[data-path='statusLabel'][data-val='Identifié']")
    wait(150)
    pg.click("[data-act=saveSpecimen]")
    wait(700)
    check("même point, même spot : la question n'est pas reposée", not sheet_open() and ev("S.specimens.find(s => s.id === S.params.id).status") == "identifie")
    # versement dans la sortie du même jour au même spot : photos libres ajoutées à la sortie
    spm = ev("S.specimens.find(s => s.id === S.params.id)")
    same_day = ev("S.sorties.filter(s => s.spotId === 'demo-s1' && s.date.slice(0, 10) === localISO().slice(0, 10)).length")
    before_ids = photo_ids()
    pg.click("[data-act=specToSortie]")
    pg.wait_for_function("S.view === 'obs'", timeout=6000)
    wait(300)
    tgt = ev("S.sorties.find(s => s.id === S.draft.sid)")
    ob = [o for o in tgt["obs"] if o["id"] == ev("S.draft.oid")][0]
    check("versé dans la sortie du jour : fiche ouverte, cinq plans, point gardé, prises libres ajoutées aux photos de la sortie",
          same_day >= 1 and len(ob["photos"]) == 5 and ob.get("lat") == 45.75 and set(spm["extra"]) <= set(tgt["photoIds"]) and photo_ids() == before_ids and ev("S.specimens.find(s => s.id === '%s').sortieId" % spm["id"]) == tgt["id"])
    pg.click("[data-act=back]")
    wait(400)
    # « Retirer le point »
    nav("specimen", "{}")
    ev("syncDraft(); Object.assign(S.draft, { lat: 45.75, lng: 0.35, acc: 8 }); render()")
    pg.select_option("#f-spot2", "demo-s1")
    pg.click("[data-act=saveSpecimen]")
    pg.wait_for_selector("#scrim", timeout=4000)
    pg.click("#scrim [data-x=no]")
    wait(700)
    check("« Retirer le point » : spécimen enregistré sans point", "lat" not in ev("S.specimens.find(s => s.id === S.params.id)"))

    # =====================================================================
    # G. Carte, hors ligne, climat, repères
    # =====================================================================
    nav("carte")
    wait(1300)
    check("tuiles Plan IGN chargées, grille validée", ev("[...document.querySelectorAll('.tile')].filter(i => i.complete && i.naturalWidth > 0).length") > 3 and ev("S.settings.tms.plan") == "PM_0_19")
    n_pts = pg.locator(".pt").count()
    check("points d'observation sur la carte", n_pts >= 6, str(n_pts))
    shot("19-carte")
    pg.click("[data-act=layer][data-val=ortho]")
    wait(1000)
    check("couche photo aérienne", ev("S.settings.layer") == "ortho")
    pg.click("[data-act=layer][data-val=plan]")
    wait(500)
    ev("S.bigMap.setView({ lat: 45.69381, lng: 0.29117 }, 18)")
    wait(500)
    pg.locator(".pt").last.click()
    wait(400)
    check("carte : fiche du point touché", pg.locator("#map-card [data-act=findObs][data-oid]").count() == 1)
    shot("20-carte-point")
    pg.click("#map-card [data-act=findObs]")
    wait(800)
    fin = pg.inner_text(".finder").lower()
    check("retrouver le point d'une observation", "point d’observation" in fin or "point d'observation" in fin, pg.inner_text("#dist"))
    nav("carte")
    wait(500)
    pg.click("[data-act=offline]")
    wait(300)
    est1 = pg.inner_text("#off-est")
    pg.click("#off-photo")
    wait(100)
    est2 = pg.inner_text("#off-est")
    pg.click("#off-photo")
    check("carte hors ligne : estimation", est1 != est2, f"{est1} / {est2}")
    pg.click("#off-go")
    pg.wait_for_function("S.offline && S.offline.n > 0", timeout=90000)
    wait(400)
    off = ev("S.offline")
    ncache = ev("caches.open('mycota-offline').then(c => c.keys()).then(k => k.length)")
    check("carte hors ligne préparée", off["n"] == ncache and off["n"] > 300 and off["fail"] == 0, f"{off['n']} tuiles")
    nav("climat")
    wait(1300)
    shot("21-climat", True)
    check("climat : repères", pg.locator("text=Tes repères").count() == 1)
    nav("spot", "{ id: 'demo-s1' }")
    wait(1300)
    shot("22-spot", True)
    check("spot : repères et pluie actuelle", pg.locator("text=Tes repères ici").count() == 1 and "mm" in pg.inner_text("#spot-now"), pg.inner_text("#spot-now"))

    # =====================================================================
    # H. Deuxième avis, exports
    # =====================================================================
    nav("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }")
    pg.click("[data-act=avisObs]")
    wait(500)
    pg.click("#av-spot")
    pg.click("#av-go")
    pg.wait_for_selector("img.preview", timeout=20000)
    wait(400)
    with pg.expect_download() as d:
        pg.click("#of-go")
    im = Image.open(d.value.path())
    check("image « deuxième avis »", im.size[0] == 1080 and im.size[1] > 1400, f"{d.value.suggested_filename} {im.size}")
    im.save(SHOTS / "23-deuxieme-avis.jpg")
    pg.click("[data-act=back]")
    wait(400)
    nav("reglages")
    pg.fill("#set-obs", "Saïd Test")
    pg.dispatch_event("#set-obs", "change")
    wait(200)
    shot("24-reglages", True)

    def dwc(button):
        pg.click("[data-act=exportDwC]")
        wait(300)
        with pg.expect_download() as dd:
            pg.click(button)
        with open(dd.value.path(), encoding="utf-8-sig", newline="") as f:
            return {r["occurrenceID"]: r for r in csv.DictReader(f)}

    ex = dwc("#dwc-exact")
    r_own = ex["mycota:demo-o0:0"]
    check("Darwin Core exact : point de l'observation, incertitude du GPS, altitude, observateur, n° de récolte",
          r_own["decimalLatitude"] == "45.693610" and r_own["coordinateUncertaintyInMeters"] == "7" and r_own["minimumElevationInMeters"] == "118" and r_own["recordedBy"] == "Saïd Test" and r_own["recordNumber"] == "SA-2026-014" and "pied du champignon" in r_own["georeferenceRemarks"]
          and r_own["taxonConceptID"] == "https://taxref.mnhn.fr/taxref-web/taxa/29388" and r_own["nameAccordingTo"] == "TAXREF v18",
          f"{r_own['decimalLatitude']} ±{r_own['coordinateUncertaintyInMeters']}")
    r_fb = ex["mycota:demo-o3:1"]
    check("Darwin Core exact : sans point propre, position du spot et incertitude de 250 m", r_fb["decimalLatitude"] == "45.693520" and r_fb["coordinateUncertaintyInMeters"] == "250" and "position du spot" in r_fb["georeferenceRemarks"], f"{r_fb['decimalLatitude']} ±{r_fb['coordinateUncertaintyInMeters']}")
    check("Darwin Core : date avec décalage horaire, identifiants stables", bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:00\+0[12]:00", r_own["eventDate"])) and f"mycota:{so['obs'][0]['id']}" in ex and "mycota:realo:0" in ex, r_own["eventDate"])
    bl = dwc("#dwc-blur")["mycota:demo-o0:0"]
    check("Darwin Core flouté : deux décimales, 1 000 m, pas de nom de spot", bl["decimalLatitude"] == "45.69" and bl["coordinateUncertaintyInMeters"] == "1000" and bl["locality"] == "")
    with pg.expect_download() as d:
        pg.click("[data-act=exportGPX]")
    gpx = open(d.value.path(), encoding="utf-8").read()
    check("GPX : spots, points et altitude", gpx.count("<wpt") >= 8 and "<ele>118</ele>" in gpx, str(gpx.count("<wpt")))

    # =====================================================================
    # I. Sauvegarde .zip, restauration (zip, zip recompressé, ancien .json)
    # =====================================================================
    STATE = """(async () => ({ n: [S.spots.length, S.sorties.length, S.specimens.length], photos: (await DB.all('photos')).map(p => [p.id, p.blob.size, p.thumb ? p.thumb.size : 0]).sort(),
      rec: JSON.stringify([S.spots, S.sorties, S.specimens].map(l => l.map(r => { const { updatedAt, ...x } = r; return x; }).sort((a, b) => a.id.localeCompare(b.id)))), notes: S.taxnotes }))()"""
    st0 = ev(STATE)
    pg.click("[data-act=exportJSON]")
    pg.wait_for_selector("#of-go", timeout=20000)
    shot("25-sauvegarde-prete")
    with pg.expect_download() as d:
        pg.click("#of-go")
    ZIP = str(WORK / "sauvegarde.zip")
    d.value.save_as(ZIP)
    z = zipfile.ZipFile(ZIP)
    names = z.namelist()
    data = json.loads(z.read("mycota.json"))
    n_ph = len(st0["photos"])
    ok_jpg = all(Image.open(io.BytesIO(z.read(n))).size[0] > 0 for n in names if n.endswith(".jpg"))
    check("sauvegarde : archive .zip valide, relevés et photos en fichiers", d.value.suggested_filename.endswith(".zip") and z.testzip() is None and data["format"] == 4 and len([n for n in names if n.startswith("photos/")]) == n_ph and len([n for n in names if n.startswith("thumbs/")]) == n_ph and ok_jpg and "boletus edulis" in data["taxnotes"],
          f"{len(names)} fichiers, {os.path.getsize(ZIP) // 1024} Ko, {n_ph} photos")
    wait(300)
    nav("carnet")
    check("sauvegarde notée : le rappel disparaît", ev("!!S.backup") and pg.locator(".notice.backup").count() == 0)

    def wipe():
        nav("reglages")
        pg.click("[data-act=wipe]")
        pg.click("#scrim [data-x=ok]")
        pg.wait_for_function("S.view === 'carnet' && S.spots.length === 0", timeout=8000)
        wait(300)
        assert ev("DB.keys('photos')") == []

    def restore(path):
        nav("reglages")
        pg.set_input_files("[data-import]", path)
        pg.wait_for_function("S.view === 'carnet' && S.spots.length > 0", timeout=30000)
        wait(400)

    wipe()
    restore(ZIP)
    st1 = ev(STATE)
    check("restauration du .zip : mêmes fiches, mêmes photos à l'octet près en taille", st1["n"] == st0["n"] and st1["photos"] == st0["photos"] and st1["rec"] == st0["rec"] and st1["notes"] == st0["notes"], f"{st1['n']} · {len(st1['photos'])} photos")
    check("carnet vide restauré : pas de rappel de sauvegarde", ev("!!S.backup") and pg.locator(".notice.backup").count() == 0)
    nav("sortie", "{ id: 'demo-o0' }")
    pg.click("[data-act=obs][data-oid='demo-o0:0']")
    wait(500)
    check("photos restaurées affichées", ev("[...document.querySelectorAll('button.plan img')].filter(i => i.complete && i.naturalWidth > 0).length") == 4)
    pg.click("[data-act=back]")
    wait(300)
    # archive défaite puis recompressée par un autre outil, dans un dossier
    ZIP2 = str(WORK / "recompresse.zip")
    with zipfile.ZipFile(ZIP2, "w", zipfile.ZIP_DEFLATED) as z2:
        for n in names:
            z2.writestr("mycota-sauvegarde/" + n, z.read(n))
        z2.writestr("__MACOSX/._mycota.json", b"x")
    wipe()
    restore(ZIP2)
    st2 = ev(STATE)
    check("restauration d'une archive recompressée dans un dossier", st2["n"] == st0["n"] and st2["photos"] == st0["photos"] and st2["rec"] == st0["rec"])
    wipe()
    restore(V3_JSON)
    v3 = ev("(async () => [S.spots.length, S.sorties.length, S.specimens.length, S.sorties.find(s => s.id === 'realo').obs.map(o => o.id), (await DB.keys('photos')).length])()")
    check("restauration d'une ancienne sauvegarde .json de la V3", v3[:3] == old[:3] and v3[3] == ["realo:0", "realo:1"] and v3[4] == 4, str(v3))
    wipe()
    restore(ZIP)
    nav("reglages")
    pg.set_input_files("[data-import]", IMG[0])
    wait(600)
    check("fichier qui n'est pas une sauvegarde : refusé sans rien toucher", "pas une sauvegarde" in toast_text() and ev("S.spots.length") == st0["n"][0], toast_text())

    # =====================================================================
    # J. Coffre : positions et saisie gardée chiffrées
    # =====================================================================
    nav("reglages")
    pg.click("[data-act=vaultOn]")
    pg.fill("#v1", "cepes2026")
    pg.fill("#v2", "cepes2026")
    pg.click("#v-ok")
    pg.wait_for_function("!!S.vault && !document.querySelector('#scrim')", timeout=20000)
    raw = ev("DB.get('sorties', 'demo-o0')")
    check("coffre : aucune coordonnée en clair dans le téléphone", "lat" not in raw["obs"][0] and "lat" not in raw and "enc" in raw)
    ev("parkDraft(); go('sortieForm', { spotId: 'demo-s1' })")
    wait(400)
    pg.fill("[data-sp='0']", "Pied-de-mouton")
    pg.dispatch_event("[data-sp='0']", "change")
    pg.click("[data-act=obsPin][data-i='0']")
    pg.wait_for_function("S.draft.obs[0] && typeof S.draft.obs[0].lat === 'number'", timeout=5000)
    wait(900)
    rawd = ev("DB.get('meta', 'draft')")
    check("coffre : la saisie gardée est chiffrée en entier", bool(rawd) and list(rawd["value"].keys()) == ["enc"])
    pg.reload()
    wait(800)
    check("écran de code au démarrage", pg.locator("#unlock-pass").count() == 1)
    ev("history.back()")
    wait(400)
    check("écran de code : le retour arrière ne le contourne pas", pg.locator("#unlock-pass").count() == 1 and ev("S.spots.length") == 0)
    pg.fill("#unlock-pass", "mauvais")
    pg.click("[data-act=unlock]")
    wait(1500)
    check("mauvais code refusé", "incorrect" in pg.inner_text("#unlock-err").lower() and pg.locator("#unlock-pass").count() == 1)
    pg.fill("#unlock-pass", "cepes2026")
    pg.click("[data-act=unlock]")
    pg.wait_for_function("S.view === 'carnet' && S.spots.length > 0", timeout=15000)
    wait(400)
    o = ev("S.sorties.find(s => s.id === 'demo-o0').obs[0]")
    check("coffre : points restaurés au déverrouillage", o.get("lat") == 45.69361 and o.get("alt") == 118)
    check("coffre : saisie gardée retrouvée après le code", pg.locator(".notice.pending").count() == 1)
    pg.click("[data-act=draftResume]")
    wait(400)
    check("coffre : reprise de la saisie avec son point", pg.input_value("[data-sp='0']") == "Pied-de-mouton" and ev("S.draft.obs[0].lat") == 45.69361)
    pg.click("[data-act=back]")
    wait(200)
    pg.click("#scrim [data-x=leave]")
    wait(400)
    check("notes personnelles conservées", "Réseau blanc" in ev("S.taxnotes['boletus edulis'] || ''"))
    nav("reglages")
    pg.click("[data-act=vaultOff]")
    pg.click("#scrim [data-x=ok]")
    pg.wait_for_function("!S.vault", timeout=10000)
    wait(500)
    check("code retiré : positions de nouveau lisibles", ev("DB.get('sorties', 'demo-o0')")["obs"][0].get("lat") == 45.69361)

    # =====================================================================
    # K. Pannes et cas limites
    # =====================================================================
    geo(seq=[7])
    nav("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }")
    pg.click("button.plan[data-target='obs:chapeau']")
    wait(250)
    pg.click("#scrim [data-x=view]")
    wait(400)
    check("plan photo : « Voir en grand »", pg.locator(".viewer img").count() == 1 and not sheet_open())
    pg.click(".viewer")
    wait(200)
    pg.click("[data-act=back]")
    wait(300)
    # ligne vide retirée sans question
    ev("parkDraft(); go('sortieForm', { spotId: 'demo-s2' })")
    wait(400)
    pg.click("text=+ Ajouter une espèce")
    wait(200)
    pg.click("[data-act=obsDel][data-i='1']")
    wait(250)
    check("ligne vide : retirée sans confirmation", not sheet_open() and ev("S.draft.obs.length") == 1)
    # position introuvable
    geo(fail=True)
    ev("S.lastPos = null")
    pg.click("[data-act=obsPin][data-i='0']")
    pg.wait_for_function("(() => { const t = document.querySelector('.toast'); return t && !t.hidden && t.textContent.includes('Position introuvable'); })()", timeout=6000)
    check("position introuvable : annoncée en quelques secondes, aucun point inventé", ev("S.draft.obs[0].lat") is None and pg.inner_text("[data-act=obsPin][data-i='0'] span") == "Point")
    geo(seq=[7])
    # téléphone plein au moment d'enregistrer
    pg.fill("[data-sp='0']", "Girolle")
    pg.dispatch_event("[data-sp='0']", "change")
    pg.set_input_files("[data-photo-in='draft'][multiple]", IMG[:2])
    pg.wait_for_function("S.draft && S.draft.photoIds.length === 2", timeout=10000)
    wait(300)
    n0 = ev("S.sorties.length")
    ev("(() => { window.__put = DB.put; DB.put = function (s, v) { return s === 'sorties' ? Promise.reject(new Error('quota')) : window.__put.call(DB, s, v); }; })()")
    pg.click("[data-act=saveSortie]")
    wait(700)
    check("téléphone plein : enregistrement refusé, annoncé, rien n'est affiché comme enregistré à tort",
          "Enregistrement impossible" in toast_text() and ev("S.sorties.length") == n0 and ev("S.view") == "sortieForm" and pg.input_value("[data-sp='0']") == "Girolle", toast_text())
    ev("(() => { DB.put = window.__put; })()")
    pg.click("[data-act=saveSortie]")
    wait(900)
    sl = ev("S.sorties.find(s => s.id === S.params.id)")
    check("nouvel essai : la sortie est enregistrée, une seule fois", ev("S.sorties.length") == n0 + 1 and len(sl["photoIds"]) == 2 and ev("S.view") == "sortie")
    # photos d'ambiance : effacées à l'enregistrement seulement
    nav("sortieForm", "{ id: '%s' }" % sl["id"])
    gone = sl["photoIds"][0]
    pg.click(f"[data-act=photoDel][data-id='{gone}']")
    wait(300)
    check("photo d'ambiance retirée : pas effacée avant l'enregistrement", gone in photo_ids() and ev("S.draft.photoIds.length") == 1)
    pg.click("[data-act=saveSortie]")
    wait(800)
    check("sortie enregistrée : la photo retirée est effacée du téléphone", gone not in photo_ids() and ev("S.sorties.find(s => s.id === '%s').photoIds.length" % sl["id"]) == 1)
    # photo refusée par le stockage
    nav("specimen", "{}")
    ev("(() => { window.__put = DB.put; DB.put = function (s, v) { return s === 'photos' ? Promise.reject(new Error('quota')) : window.__put.call(DB, s, v); }; })()")
    pg.set_input_files("label.plan [data-photo-in='step:chapeau']", IMG[0])
    wait(1500)
    check("téléphone plein : la photo refusée est annoncée", "Photo non enregistrée" in toast_text() and ev("Object.keys(S.draft.photos).length") == 0, toast_text())
    ev("(() => { DB.put = window.__put; })()")
    pg.click("[data-act=back]")
    wait(300)
    # photo rapide sans GPS
    nav("carnet")
    geo(fail=True)
    ev("S.lastPos = null")
    n_sp = ev("S.specimens.length")
    pg.click(".fab")
    wait(300)
    pg.set_input_files("[data-quick]", IMG[1])
    pg.wait_for_function("n => S.specimens.length === n + 1 && S.view === 'specimen'", arg=n_sp, timeout=12000)
    wait(200)
    qs = ev("S.specimens.find(s => s.id === S.params.id)")
    check("photo rapide sans GPS : fiche créée quand même, sans point", bool(qs["photos"].get("chapeau")) and "lat" not in qs and "pas disponible" in toast_text(), toast_text())
    geo(seq=[7])
    # saisie en attente d'une fiche supprimée
    nav("obs", "{ sid: '%s', oid: '%s' }" % (sl["id"], sl["obs"][0]["id"]))
    pg.fill("#o-ouv", "à jeter")
    wait(800)
    nav("carnet")
    seen = pg.locator(".notice.pending").count() == 1
    ev("deleteRec('sortie', '%s').then(render)" % sl["id"])
    wait(500)
    check("sortie supprimée : sa saisie en attente disparaît avec elle", seen and ev("S.pendingDraft") is None and ev("DB.get('meta', 'draft')") is None and pg.locator(".notice.pending").count() == 0)
    nav("spotForm", "{}")
    pg.fill("#f-name", "Brouillon")
    wait(800)
    nav("carnet")
    pg.click("[data-act=draftDrop]")
    wait(250)
    asked = sheet_open() and "Jeter cette saisie" in pg.inner_text("#scrim")
    pg.click("#scrim [data-x=ok]")
    wait(500)
    check("saisie en attente jetée depuis le Carnet, après confirmation", asked and ev("S.pendingDraft") is None and pg.locator(".notice.pending").count() == 0)
    # spécimen versé sans sortie existante ce jour-là
    ph1, ph2 = ev(MKPHOTO, "#775533"), ev(MKPHOTO, "#335577")
    ev("""async ([a, b]) => { await saveRec('specimen', { id: 'mold', date: '2026-09-12T10:00', spotId: 'demo-s2', photos: { chapeau: a }, extra: [b], odeur: '', sporee: 'Blanche', hypothese: 'Pied-de-mouton', latin: 'Hydnum repandum', notes: '', status: 'identifie' }); }""", [ph1, ph2])
    nav("specimen", "{ id: 'mold' }")
    pg.click("[data-act=specToSortie]")
    pg.wait_for_function("S.view === 'obs'", timeout=6000)
    wait(300)
    ns = ev("S.sorties.find(s => s.id === S.draft.sid)")
    check("spécimen versé un jour sans sortie : une sortie est créée à sa date, avec ses photos",
          ns["date"] == "2026-09-12T10:00" and ns["spotId"] == "demo-s2" and ns["photoIds"] == [ph2] and ns["obs"][0]["photos"] == {"chapeau": ph1} and "Sporée" in ns["obs"][0]["methodes"])
    pg.click("[data-act=back]")
    wait(300)
    # sauvegardes abîmées ou étrangères
    nav("reglages")
    raw_zip = open(ZIP, "rb").read()
    bad = [str(WORK / "tronquee.zip"), str(WORK / "autre.zip"), str(WORK / "autre.json")]
    open(bad[0], "wb").write(raw_zip[: len(raw_zip) * 6 // 10])
    with zipfile.ZipFile(bad[1], "w") as zz:
        zz.writestr("notes.txt", "rien")
    open(bad[2], "w").write(json.dumps({"app": "Autre", "spots": []}))
    COUNT = "JSON.stringify([S.spots.length, S.sorties.length, S.specimens.length])"
    snap, msgs = ev(COUNT), []
    for f in bad:
        pg.set_input_files("[data-import]", f)
        wait(500)
        msgs.append(toast_text())
    check("sauvegardes abîmées ou étrangères : refusées, carnet intact", all("pas une sauvegarde" in m for m in msgs) and ev(COUNT) == snap and ev("S.view") == "reglages", str(msgs))
    ms = ev("(() => { S.codexF = { mode: 'tout', q: '', list: 'charente', sort: 'num' }; parkDraft(); go('codex', {}); const t = performance.now(); for (let i = 0; i < 5; i++) renderDex(); return (performance.now() - t) / 5; })()")
    check("Mycodex Charente : 424 cases redessinées vite, listes dérivées gardées en mémoire", ms < 300 and ev("codexIndex() === codexIndex() && allObs() === allObs()"), f"{ms:.0f} ms par dessin")
    ev("S.codexF.list = 'depart'")

    # =====================================================================
    # L. Mise en page : sombre, petit écran
    # =====================================================================
    pg.emulate_media(color_scheme="dark")
    for t, prm in [("carnet", "{}"), ("codex", "{}"), ("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }"), ("taxon", "{ key: 'amanita phalloides' }")]:
        nav(t, prm)
        wait(400)
        shot(f"26-sombre-{t}")
    pg.emulate_media(color_scheme="light")
    pg.set_viewport_size({"width": 340, "height": 720})
    ow = []
    for t, prm in [("carnet", "{}"), ("codex", "{}"), ("bilan", "{}"), ("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }"), ("specimen", "{}"), ("carte", "{}"), ("climat", "{}"), ("reglages", "{}"),
                   ("taxon", "{ key: 'boletus edulis' }"), ("spot", "{ id: 'demo-s1' }"), ("sortieForm", "{}"), ("sortie", "{ id: 'demo-o0' }"), ("rubans", "{}"), ("chrono", "{}")]:
        nav(t, prm)
        if ev("document.documentElement.scrollWidth > window.innerWidth"):
            ow.append(t)
    check("aucun débordement horizontal à 340 px de large", not ow, str(ow))
    nav("obs", "{ sid: 'demo-o0', oid: 'demo-o0:0' }")
    shot("27-etroit-fiche", True)
    nav("carnet")

    # ---------- bascule de grille IGN (autre téléphone, serveur qui refuse la première grille) ----------
    ctx2 = b.new_context(viewport={"width": 390, "height": 844}, locale="fr-FR")
    ctx2.add_init_script(GEO)
    ctx2.route("**/*", route)
    p2 = ctx2.new_page()
    p2.on("pageerror", lambda e: errors.append("PAGEERROR2 " + str(e)))
    FAIL_PM019[0] = True
    p2.goto(f"{BASE}/new/index.html")
    p2.wait_for_timeout(800)
    p2.evaluate("loadDemo().then(() => go('carte', {}))")
    p2.wait_for_timeout(2500)
    check("carte : bascule de grille PM_0_19 vers PM si le serveur refuse la première", p2.evaluate("S.settings.tms && S.settings.tms.plan") == "PM", f"refus {calls['pm019']}, grille PM {calls['pm']}")
    check("premier lancement sur un téléphone vierge : carnet vide lisible", p2.evaluate("S.loadOk") is True)
    FAIL_PM019[0] = False

    # ---------- carnet chiffré sous V3, ouvert par la V4 ----------
    ctx3 = b.new_context(viewport={"width": 390, "height": 844}, locale="fr-FR", timezone_id="Europe/Paris")
    ctx3.add_init_script(GEO)
    ctx3.route("**/*", route)
    p3 = ctx3.new_page()
    p3.on("pageerror", lambda e: errors.append("PAGEERROR3 " + str(e)))
    p3.goto(f"{BASE}/old/index.html")
    p3.wait_for_timeout(700)
    p3.evaluate("""(async () => { await loadDemo(); await saveRec('sortie', { id: 'vo', spotId: 'demo-s1', date: '2026-10-21T09:00', photoIds: [], meteo: { sol: '', ciel: [], text: '' }, notes: '',
      obs: [{ species: 'Girolle', latin: 'Cantharellus cibarius', count: 3, weight: '', photos: {} }, { species: 'Pied bleu', latin: 'Lepista nuda', count: 2, weight: '', photos: {}, lat: 45.70012, lng: 0.30034, acc: 9, alt: 97 }] }); go('reglages', {}); })()""")
    p3.wait_for_timeout(500)
    p3.click("[data-act=vaultOn]")
    p3.fill("#v1", "cepes2026")
    p3.fill("#v2", "cepes2026")
    p3.click("#v-ok")
    p3.wait_for_function("!!S.vault && !document.querySelector('#scrim')", timeout=20000)
    p3.goto(f"{BASE}/new/index.html")
    p3.wait_for_timeout(800)
    p3.fill("#unlock-pass", "cepes2026")
    p3.click("[data-act=unlock]")
    p3.wait_for_function("S.view === 'carnet' && S.sorties.length > 0", timeout=15000)
    p3.wait_for_timeout(500)
    vo, raw = p3.evaluate("S.sorties.find(s => s.id === 'vo')"), p3.evaluate("DB.get('sorties', 'vo')")
    check("carnet chiffré sous V3 : points intacts après migration, toujours chiffrés dans le téléphone",
          [o["id"] for o in vo["obs"]] == ["vo:0", "vo:1"] and vo["obs"][1].get("lat") == 45.70012 and vo["obs"][1].get("alt") == 97 and "lat" not in vo["obs"][0]
          and [o.get("id") for o in raw["obs"]] == ["vo:0", "vo:1"] and all("lat" not in o for o in raw["obs"]) and "enc" in raw and p3.evaluate("S.spots.find(s => s.id === 'demo-s1').lat") == 45.69352)

    # ---------- navigateur qui refuse le stockage : l'app reste utilisable et le dit ----------
    ctx4 = b.new_context(viewport={"width": 390, "height": 844}, locale="fr-FR")
    ctx4.add_init_script(GEO + "Object.defineProperty(window, 'indexedDB', { configurable: true, get() { throw new Error('stockage refusé'); } });")
    ctx4.route("**/*", route)
    p4 = ctx4.new_page()
    p4.on("pageerror", lambda e: errors.append("PAGEERROR4 " + str(e)))
    p4.goto(f"{BASE}/new/index.html")
    p4.wait_for_timeout(1000)
    msg = p4.evaluate("document.querySelector('.toast')?.textContent || ''")
    p4.evaluate("loadDemo().then(() => go('carnet', {}, { replace: true }))")
    p4.wait_for_timeout(500)
    pid = p4.evaluate(MKPHOTO, "#446688")
    r4 = p4.evaluate("async id => [!!DB.mem, (await DB.keys('photos')).includes(id), await sweepPhotos(), S.spots.length]", pid)
    check("stockage refusé par le navigateur : annoncé, carnet utilisable en mémoire", "Stockage indisponible" in msg and r4 == [True, True, 0, 3], f"{msg} {r4}")
    b.close()

srv.shutdown()
shutil.rmtree(WORK, ignore_errors=True)
check("aucune erreur JavaScript pendant tout l'essai", not errors, str(errors[:5]))
check("aucune requête vers un service non prévu", not calls["autres"], str(calls["autres"][:5]))
bad = [k for k, v in results.items() if not v]
print(f"\nRÉSUMÉ : {sum(results.values())} / {len(results)} vérifications réussies")
if bad:
    print("ÉCHECS :", *bad, sep="\n  - ")
    sys.exit(1)
