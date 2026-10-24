/* Mycota — service worker : l'app s'ouvre sans réseau, les tuiles déjà vues restent consultables. */
const SHELL_CACHE = 'mycota-shell-2.1.0';
const TILE_CACHE = 'mycota-tiles';
const FONT_CACHE = 'mycota-fonts';
const MAX_TILES = 900;
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png', './apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL_CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('mycota-shell-') && k !== SHELL_CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function trimTiles() {
  const c = await caches.open(TILE_CACHE);
  const keys = await c.keys();
  for (let i = 0; i < keys.length - MAX_TILES; i++) await c.delete(keys[i]);
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Tuiles OpenStreetMap : cache d'abord, réseau ensuite (seules les tuiles déjà affichées sont gardées).
  if (url.hostname === 'tile.openstreetmap.org') {
    e.respondWith(caches.open(TILE_CACHE).then(async c => {
      const hit = await c.match(req);
      if (hit) return hit;
      try {
        const res = await fetch(req);
        if (res.ok) { c.put(req, res.clone()); trimTiles(); }
        return res;
      } catch { return new Response('', { status: 504 }); }
    }));
    return;
  }

  // Polices : servies depuis le cache, rafraîchies en arrière-plan.
  if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    e.respondWith(caches.open(FONT_CACHE).then(async c => {
      const hit = await c.match(req);
      const net = fetch(req).then(res => { c.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }

  // Météo : toujours le réseau, l'app garde son propre dernier relevé.
  if (url.origin !== self.location.origin) return;

  // Page : réseau d'abord pour recevoir les mises à jour, cache hors ligne.
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(res => {
      caches.open(SHELL_CACHE).then(c => c.put('./index.html', res.clone()));
      return res;
    }).catch(() => caches.match('./index.html')));
    return;
  }

  e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
});
