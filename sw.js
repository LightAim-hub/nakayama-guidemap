/* なかやま商店街マップ — オフライン用の控え
   2026-08-04: 現地は電波が切れる場所がある。圏外にすると真っ白になり、
   一度見たページすら出せなかったので、見たものを端末に控えておく。
   本文(HTML)は必ず新しい方を先に取りに行く。古い内容を掴んだまま
   固まらないよう、版が上がったら古い控えは捨てる。 */
const VERSION = 'nakayama-v1';
const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './assets/icon-192.png',
  './assets/icon-512.png',
  './assets/fonts/zen-maru-gothic-400.woff2',
  './assets/fonts/zen-maru-gothic-700.woff2',
  './assets/fonts/yusei-magic-400.woff2'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(VERSION)
      .then(cache => cache.addAll(SHELL).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;
  const isDoc = req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html');

  if (isDoc) {
    // 本文は新しい方を優先。取れない時だけ控えを出す。
    event.respondWith(
      fetch(req)
        .then(res => {
          if (sameOrigin && res.ok) {
            const copy = res.clone();
            caches.open(VERSION).then(c => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then(hit => hit || caches.match('./index.html')))
    );
    return;
  }

  // 画像・フォント等は控えがあれば即出し、裏で新しいものを取っておく。
  event.respondWith(
    caches.match(req).then(hit => {
      const net = fetch(req).then(res => {
        if (res && (res.ok || res.type === 'opaque')) {
          const copy = res.clone();
          caches.open(VERSION).then(c => c.put(req, copy));
        }
        return res;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
