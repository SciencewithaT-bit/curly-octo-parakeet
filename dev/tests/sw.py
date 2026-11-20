"""Mycota — essai du service worker (Chromium) : ouverture sur réseau lent, tuiles gardées, ouverture sans réseau.

  python3 dev/build.py && python3 dev/tests/sw.py [dossier de la V4 construite]"""
import http.server
import io
import os
import pathlib
import sys
import threading
import time

os.environ["PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS"] = "1"
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = str(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "pwa")
PORT = 8783
SLOW = [0]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIST, **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if SLOW[0] and self.path.split("?")[0] in ("/", "/index.html"):
            time.sleep(SLOW[0])
        return super().do_GET()


srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
b = io.BytesIO()
Image.new("RGB", (256, 256), (200, 220, 190)).save(b, "PNG")
PNG = b.getvalue()
seen = {"ign": 0}


def route(r):
    u = r.request.url
    if "data.geopf.fr" in u:
        seen["ign"] += 1
        return r.fulfill(status=200, content_type="image/png", headers={"Access-Control-Allow-Origin": "*"}, body=PNG)
    if f"localhost:{PORT}" in u or f"127.0.0.1:{PORT}" in u:
        return r.continue_()
    return r.abort()


ok = {}


def check(n, c, info=""):
    ok[n] = bool(c)
    print(("OK   " if c else "FAIL ") + n, f"· {info}" if info != "" else "", flush=True)


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844})
    ctx.route("**/*", route)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://localhost:{PORT}/")
    pg.wait_for_timeout(800)
    pg.evaluate("navigator.serviceWorker.register('./sw.js').then(() => navigator.serviceWorker.ready)")
    pg.wait_for_timeout(1200)
    pg.reload()
    pg.wait_for_timeout(1000)
    check("le service worker contrôle la page", pg.evaluate("!!navigator.serviceWorker.controller"))
    keys = pg.evaluate("caches.keys()")
    check("cache de l'app créé, au nom de la version", any(k.startswith("mycota-shell-") for k in keys), str(keys))
    # 1. Réseau très lent : l'app doit s'ouvrir depuis le cache en 2,5 s environ
    SLOW[0] = 7
    t0 = time.time()
    pg.reload(wait_until="domcontentloaded")
    dt = time.time() - t0
    pg.wait_for_selector("#app h1", timeout=10000)
    check("ouverture rapide malgré un réseau lent", dt < 4.5, f"{dt:.1f} s")
    SLOW[0] = 0
    pg.wait_for_timeout(7000)
    # 2. Tuiles IGN : gardées au passage
    pg.evaluate("loadDemo().then(() => go('carte', {}))")
    pg.wait_for_timeout(2500)
    n_tiles = pg.evaluate("caches.open('mycota-tiles').then(c => c.keys()).then(k => k.length)")
    check("tuiles IGN gardées par le service worker", n_tiles > 3, f"{n_tiles} tuiles, {seen['ign']} requêtes")
    url = pg.evaluate("tileURL('plan', 16, 32820, 23219)")
    pg.evaluate("""async u => { const c = await caches.open('mycota-offline'); const png = await (await fetch('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')).blob(); await c.put(u, new Response(png, { headers: { 'Content-Type': 'image/png' } })); }""", url)
    # 3. Serveur coupé : l'app s'ouvre quand même, la tuile préparée s'affiche
    srv.shutdown()
    srv.server_close()
    ctx.unroute("**/*")
    ctx.route("**/*", lambda r: r.abort())
    pg.reload()
    pg.wait_for_timeout(1500)
    check("ouverture sans réseau", pg.locator("#app h1").count() >= 1, pg.inner_text("#app h1") if pg.locator("#app h1").count() else "")
    loaded = pg.evaluate("""u => new Promise(r => { const i = new Image(); i.crossOrigin = 'anonymous'; i.onload = () => r(i.naturalWidth); i.onerror = () => r(-1); i.src = u; })""", url)
    check("tuile de la carte hors ligne servie sans réseau", loaded == 1, str(loaded))
    check("aucune erreur JavaScript", not errs, str(errs))
    br.close()

print(f"\nRÉSUMÉ : {sum(ok.values())} / {len(ok)} vérifications réussies")
sys.exit(0 if all(ok.values()) else 1)
