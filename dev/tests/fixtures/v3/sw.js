/* Mycota — service worker
   L'app s'ouvre vite même avec une barre de réseau, les tuiles déjà vues restent consultables,
   et la carte préparée hors ligne (tuiles IGN autour des spots) vit dans son propre cache. */
const SHELL_CACHE = 'mycota-shell-3.0.0';
const TILE_CACHE = 'mycota-tiles';
const OFFLINE_CACHE = 'mycota-offline';
const FONT_CACHE = 'mycota-fonts';
const MAX_TILES = 1500;
const NAV_TIMEOUT = 2500;
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

let trimming = false;
async function trimTiles() {
  if (trimming) return; trimming = true;
  try {
    const c = await caches.open(TILE_CACHE);
    const keys = await c.keys();
    for (let i = 0; i < keys.length - MAX_TILES; i++) await c.delete(keys[i]);
  } finally { trimming = false; }
}

const isTile = url => url.hostname === 'tile.openstreetmap.org' || (url.hostname === 'data.geopf.fr' && url.pathname.startsWith('/wmts'));

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Tuiles (OpenStreetMap, IGN) : cache d'abord, y compris la carte préparée hors ligne, réseau ensuite.
  if (isTile(url)) {
    e.respondWith((async () => {
      const hit = await caches.match(req, { ignoreVary: true });
      if (hit) return hit;
      try {
        const res = await fetch(req);
        if (res.ok) { const copy = res.clone(); caches.open(TILE_CACHE).then(c => c.put(req, copy)).then(trimTiles).catch(() => {}); }
        return res;
      } catch { return new Response('', { status: 504 }); }
    })());
    return;
  }

  // Polices : servies depuis le cache, rafraîchies en arrière-plan.
  if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    e.respondWith(caches.open(FONT_CACHE).then(async c => {
      const hit = await c.match(req);
      const net = fetch(req).then(res => { if (res.ok || res.type === 'opaque') c.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }

  // Météo et autres services : toujours le réseau, l'app garde son propre dernier relevé.
  if (url.origin !== self.location.origin) return;

  // Page : le réseau s'il répond vite (mise à jour), sinon la version gardée, qui sera remplacée en arrière-plan.
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      const cached = await caches.match('./index.html');
      const net = fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(SHELL_CACHE).then(c => c.put('./index.html', copy)).catch(() => {}); }
        return res;
      });
      if (!cached) return net.catch(() => new Response('Mycota a besoin du réseau pour sa toute première ouverture.', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } }));
      const quick = await Promise.race([net.catch(() => null), new Promise(r => setTimeout(() => r(null), NAV_TIMEOUT))]);
      if (!quick) e.waitUntil(net.catch(() => null));
      return quick && quick.ok ? quick : cached;
    })());
    return;
  }

  e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
});
